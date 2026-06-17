import asyncio
import hashlib
import importlib
import json
import os
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
sys.path.append('..')
import pptagent.induct as induct
import pptagent.pptgen as pptgen
from pptagent.document import Document
from pptagent.model_utils import ModelManager, parse_pdf
from pptagent.multimodal import ImageLabler
from pptagent.presentation import Presentation
from pptagent.utils import Config, get_logger, is_image_path, package_join, pjoin, ppt_to_images_async

# constants
DEBUG = True if len(sys.argv) == 1 else False
RUNS_DIR = os.path.abspath('..') + "/runs"

PIPELINE_STAGES = [
    {
        "id": "init",
        "label": "任务初始化",
        "inputs": ["上传 PDF/PPTX", "目标页数"],
        "outputs": ["task.json"],
        "artifacts": ["task"],
        "agents": [],
    },
    {
        "id": "ppt_parse",
        "label": "参考 PPT 解析",
        "inputs": ["source.pptx"],
        "outputs": ["slide_images/", "image_stats.json"],
        "artifacts": ["slide_images", "image_stats"],
        "agents": [],
    },
    {
        "id": "pdf_parse",
        "label": "PDF 解析",
        "inputs": ["source.pdf"],
        "outputs": ["source.md", "meta.json", "PDF 提取图片"],
        "artifacts": ["source_md", "meta", "pdf_images"],
        "agents": [],
    },
    {
        "id": "doc_refine",
        "label": "文档结构化",
        "inputs": ["source.md"],
        "outputs": ["refined_doc.json"],
        "artifacts": ["refined_doc"],
        "agents": ["doc_extractor"],
    },
    {
        "id": "template_prep",
        "label": "版式模板图",
        "inputs": ["presentation 布局结构"],
        "outputs": ["template.pptx", "template_images/"],
        "artifacts": ["template_images"],
        "agents": [],
    },
    {
        "id": "slide_induction",
        "label": "模板分析",
        "inputs": ["slide_images", "template_images", "PPT 结构"],
        "outputs": ["slide_induction.json"],
        "artifacts": ["slide_induction"],
        "agents": ["schema_extractor"],
    },
    {
        "id": "outline",
        "label": "大纲生成",
        "inputs": ["refined_doc.json", "slide_induction.json"],
        "outputs": ["outline.json"],
        "artifacts": ["outline"],
        "agents": ["planner"],
    },
    {
        "id": "slide_gen",
        "label": "逐页生成",
        "inputs": ["outline.json", "参考模板"],
        "outputs": ["各页 SlidePage"],
        "artifacts": ["slide_gen_status"],
        "agents": [
            "content_organizer",
            "layout_selector",
            "editor",
            "coder",
        ],
    },
    {
        "id": "done",
        "label": "完成",
        "inputs": [],
        "outputs": ["final.pptx"],
        "artifacts": ["final"],
        "agents": [],
    },
]

STAGE_TRACE_FILES = {
    "doc_refine": "doc_extractor",
    "slide_induction": "schema_extractor",
    "outline": "planner",
    "slide_gen": "slide_gen",
}

TRACE_TEXT_LIMIT = 8192

STAGE_IDS = [s["id"] for s in PIPELINE_STAGES]
STAGE_BY_ID = {s["id"]: s for s in PIPELINE_STAGES}

models = ModelManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    assert await models.test_connections(), "Model connection test failed"
    yield


# server
logger = get_logger(__name__)
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
progress_store: dict[str, dict] = {}
active_connections: dict[str, WebSocket] = {}
human_review_futures: dict[str, asyncio.Future] = {}


def normalize_task_id(task_id: str) -> str:
    return task_id.replace("|", "/")


def task_api_id(task_id: str) -> str:
    return task_id.replace("/", "|")


def pipeline_state_path(task_id: str) -> str:
    return pjoin(RUNS_DIR, normalize_task_id(task_id), "pipeline_state.json")


def preview_dir(preview_id: str) -> str:
    safe_id = preview_id.replace("/", "_").replace("..", "_")
    return pjoin(RUNS_DIR, "preview", safe_id)


def preview_slide_dir(preview_id: str) -> str:
    pptx_slide_dir = pjoin(RUNS_DIR, "pptx", preview_id, "slide_images")
    if os.path.isdir(pptx_slide_dir):
        return pptx_slide_dir
    return pjoin(preview_dir(preview_id), "slide_images")


def agent_traces_dir(task_id: str) -> str:
    return pjoin(RUNS_DIR, normalize_task_id(task_id), "agent_traces")


def human_review_path(task_id: str) -> str:
    return pjoin(RUNS_DIR, normalize_task_id(task_id), "human_review.json")


def save_agent_trace(task_id: str, name: str, data: Any):
    trace_dir = agent_traces_dir(task_id)
    os.makedirs(trace_dir, exist_ok=True)
    safe_name = name.replace("/", "_").replace("..", "_")
    json.dump(
        data,
        open(pjoin(trace_dir, f"{safe_name}.json"), "w"),
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def truncate_trace_value(value: Any, limit: int = TRACE_TEXT_LIMIT) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "\n\n...(truncated)"
    if isinstance(value, list):
        return [truncate_trace_value(item, limit) for item in value]
    if isinstance(value, dict):
        return {k: truncate_trace_value(v, limit) for k, v in value.items()}
    return value


def load_task_config(task_id: str) -> dict:
    path = pjoin(RUNS_DIR, normalize_task_id(task_id), "task.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Task not found")
    return json.load(open(path))


def save_pipeline_state(task_id: str, state: dict):
    path = pipeline_state_path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(state, open(path, "w"), ensure_ascii=False, indent=2)


def init_pipeline_state(task_id: str, generation_mode: str = "auto") -> dict:
    state = {
        "task_id": task_api_id(task_id),
        "generation_mode": generation_mode,
        "awaiting_human": None,
        "started_at": time.time(),
        "elapsed_ms": 0,
        "current_stage_id": None,
        "stages": {
            stage["id"]: {
                "id": stage["id"],
                "label": stage["label"],
                "inputs": stage["inputs"],
                "outputs": stage["outputs"],
                "agents": stage.get("agents", []),
                "status": "pending",
                "elapsed_ms": None,
                "summary": None,
                "cached": False,
            }
            for stage in PIPELINE_STAGES
        },
        "slide_gen": {"slides": [], "completed": 0, "total": 0},
        "stage_subprogress": {},
    }
    save_pipeline_state(task_id, state)
    return state


class ProgressManager:
    def __init__(
        self,
        task_id: str,
        run_dir: str,
        generation_mode: str = "auto",
        debug: bool = True,
    ):
        self.task_id = task_id
        self.run_dir = run_dir
        self.debug = debug
        self.failed = False
        self.pipeline_started_at = time.monotonic()
        self.stage_started_at: dict[str, float] = {}
        self.state = init_pipeline_state(task_id, generation_mode)
        self.current_stage_id: Optional[str] = None

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self.pipeline_started_at) * 1000)

    def _stage_elapsed_ms(self, stage_id: str) -> Optional[int]:
        if stage_id not in self.stage_started_at:
            return None
        return int((time.monotonic() - self.stage_started_at[stage_id]) * 1000)

    def _artifact_urls(self, stage_id: str) -> list[dict]:
        stage = STAGE_BY_ID[stage_id]
        tid = task_api_id(self.task_id)
        return [
            {
                "key": key,
                "type": "json" if key not in ("slide_images", "template_images", "pdf_images", "final") else "files",
                "url": f"/api/task/{tid}/artifact/{key}",
            }
            for key in stage.get("artifacts", [])
        ]

    def _stage_index(self, stage_id: str) -> int:
        return STAGE_IDS.index(stage_id) + 1

    def _progress_percent(self, stage_id: str, stage_status: str) -> int:
        idx = STAGE_IDS.index(stage_id)
        if stage_status == "completed":
            return int(((idx + 1) / len(STAGE_IDS)) * 100)
        return int((idx / len(STAGE_IDS)) * 100)

    async def _push(self, stage_id: str, stage_status: str, summary: Optional[dict] = None):
        stage = STAGE_BY_ID[stage_id]
        self.state["elapsed_ms"] = self._elapsed_ms()
        self.state["current_stage_id"] = stage_id
        if stage_id in self.state["stages"]:
            self.state["stages"][stage_id]["status"] = stage_status
            if summary is not None:
                self.state["stages"][stage_id]["summary"] = summary
            if stage_status in ("completed", "failed"):
                self.state["stages"][stage_id]["elapsed_ms"] = self._stage_elapsed_ms(stage_id)

        save_pipeline_state(self.task_id, self.state)

        websocket = active_connections.get(self.task_id)
        if websocket is None:
            logger.info(
                "websocket is None, stage=%s status=%s", stage_id, stage_status
            )
            return

        payload = {
            "progress": self._progress_percent(stage_id, stage_status),
            "status": stage["label"],
            "stage_id": stage_id,
            "stage_index": self._stage_index(stage_id),
            "total_stages": len(STAGE_IDS),
            "stage_status": stage_status,
            "elapsed_ms": self._elapsed_ms(),
            "stage_elapsed_ms": self._stage_elapsed_ms(stage_id),
            "inputs": stage["inputs"],
            "outputs": stage["outputs"],
            "summary": summary or self.state["stages"][stage_id].get("summary"),
            "artifacts": self._artifact_urls(stage_id) if stage_status == "completed" else [],
            "pipeline": self.state,
        }
        await websocket.send_json(payload)

    async def report_stage_start(self, stage_id: str):
        self.current_stage_id = stage_id
        self.stage_started_at[stage_id] = time.monotonic()
        if self.task_id not in active_connections:
            logger.warning("WebSocket disconnected, stage %s still running", stage_id)
        await self._push(stage_id, "running")

    async def report_stage_complete(
        self, stage_id: str, summary: Optional[dict] = None, cached: bool = False
    ):
        if summary is None:
            summary = {}
        summary["cached"] = cached
        self.state["stages"][stage_id]["cached"] = cached
        await self._push(stage_id, "completed", summary)

    async def report_stage_waiting(self, stage_id: str, summary: Optional[dict] = None):
        if summary is None:
            summary = {}
        self.current_stage_id = stage_id
        await self._push(stage_id, "waiting", summary)

    async def report_subprogress(self, stage_id: str, sub: dict):
        if stage_id == "slide_gen":
            self.state["slide_gen"].update(sub)
        else:
            self.state.setdefault("stage_subprogress", {})[stage_id] = sub
        save_pipeline_state(self.task_id, self.state)
        websocket = active_connections.get(self.task_id)
        if websocket is None:
            return
        stage = STAGE_BY_ID[stage_id]
        payload = {
            "progress": self._progress_percent(stage_id, "running"),
            "status": stage["label"],
            "stage_id": stage_id,
            "stage_index": self._stage_index(stage_id),
            "total_stages": len(STAGE_IDS),
            "stage_status": "running",
            "elapsed_ms": self._elapsed_ms(),
            "stage_elapsed_ms": self._stage_elapsed_ms(stage_id),
            "subprogress": sub,
            "pipeline": self.state,
        }
        await websocket.send_json(payload)

    async def fail_stage(self, error_message: str):
        stage_id = self.current_stage_id or STAGE_IDS[0]
        self.state["stages"][stage_id]["status"] = "failed"
        self.state["stages"][stage_id]["summary"] = {"error": error_message}
        self.failed = True
        save_pipeline_state(self.task_id, self.state)

        websocket = active_connections.get(self.task_id)
        if websocket is not None:
            stage = STAGE_BY_ID[stage_id]
            await websocket.send_json(
                {
                    "progress": 100,
                    "status": f"{stage['label']} 失败",
                    "stage_id": stage_id,
                    "stage_index": self._stage_index(stage_id),
                    "total_stages": len(STAGE_IDS),
                    "stage_status": "failed",
                    "elapsed_ms": self._elapsed_ms(),
                    "summary": {"error": error_message},
                    "pipeline": self.state,
                }
            )
        active_connections.pop(self.task_id, None)
        if self.debug:
            logger.error("%s: stage %s failed: %s", self.task_id, stage_id, error_message)


async def run_blocking_with_heartbeat(
    progress: "ProgressManager",
    stage_id: str,
    func,
    *args,
    interval_sec: float = 3.0,
    message: str = "处理中...",
    **kwargs,
):
    """Run blocking work in a thread while keeping the event loop alive for progress updates."""
    task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    while not task.done():
        await progress.report_subprogress(
            stage_id,
            {"message": message, "running": True},
        )
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    return task.result()


def list_images_in_dir(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    return sorted(
        f for f in os.listdir(folder) if is_image_path(pjoin(folder, f))
    )


def normalize_preview_id(preview_id: str) -> str:
    if ".." in preview_id or "/" in preview_id or "\\" in preview_id:
        raise HTTPException(status_code=400, detail="Invalid preview id")
    return preview_id


def normalize_outline_edits(raw_outline: Any, expected_count: int) -> list[dict]:
    if not isinstance(raw_outline, list):
        raise HTTPException(status_code=400, detail="outline must be a list")
    if len(raw_outline) != expected_count:
        raise HTTPException(status_code=400, detail="outline length does not match")

    normalized = []
    for idx, item in enumerate(raw_outline, 1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"outline item {idx} is invalid")
        purpose = str(item.get("purpose", "")).strip()
        section = str(item.get("section", "")).strip()
        if not purpose or not section:
            raise HTTPException(
                status_code=400,
                detail=f"第 {idx} 页的 purpose 和 section 均不能为空",
            )
        normalized.append(
            {
                "slide": idx,
                "purpose": purpose,
                "section": section,
            }
        )
    return normalized


async def wait_for_outline_review(
    progress: "ProgressManager",
    task_id: str,
    outline: list[dict],
) -> list[dict]:
    review_path = human_review_path(task_id)
    review_data = {
        "task_id": task_api_id(task_id),
        "type": "outline",
        "status": "waiting",
        "outline": outline,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    json.dump(review_data, open(review_path, "w"), ensure_ascii=False, indent=2)

    progress.state["awaiting_human"] = {
        "type": "outline",
        "stage_id": "outline",
        "status": "waiting",
        "url": f"/api/task/{task_api_id(task_id)}/human-review",
        "updated_at": time.time(),
    }
    await progress.report_stage_waiting(
        "outline",
        {
            "message": "等待确认大纲",
            "total_slides": len(outline),
            "outline_preview": outline[:5],
        },
    )

    future = asyncio.get_running_loop().create_future()
    human_review_futures[task_id] = future
    try:
        edited_outline = await future
    finally:
        human_review_futures.pop(task_id, None)

    progress.state["awaiting_human"] = None
    return edited_outline


def resolve_artifact_path(task_id: str, artifact_name: str) -> tuple[str, str]:
    """Return (absolute_path, media_type). Raises HTTPException if invalid."""
    task_id = normalize_task_id(task_id)
    task = load_task_config(task_id)
    pptx_dir = pjoin(RUNS_DIR, "pptx", task["pptx"])
    pdf_dir = pjoin(RUNS_DIR, "pdf", task["pdf"])
    task_dir = pjoin(RUNS_DIR, task_id)

    if artifact_name == "task":
        return pjoin(task_dir, "task.json"), "application/json"
    if artifact_name == "image_stats":
        return pjoin(pptx_dir, "image_stats.json"), "application/json"
    if artifact_name == "source_md":
        return pjoin(pdf_dir, "source.md"), "text/markdown"
    if artifact_name == "meta":
        return pjoin(pdf_dir, "meta.json"), "application/json"
    if artifact_name == "refined_doc":
        return pjoin(pdf_dir, "refined_doc.json"), "application/json"
    if artifact_name == "slide_induction":
        return pjoin(pptx_dir, "slide_induction.json"), "application/json"
    if artifact_name == "outline":
        return pjoin(task_dir, "outline.json"), "application/json"
    if artifact_name == "final":
        return pjoin(task_dir, "final.pptx"), "application/pptx"
    if artifact_name.startswith("slide_image/"):
        fname = artifact_name.split("/", 1)[1]
        if ".." in fname or "/" in fname:
            raise HTTPException(status_code=400, detail="Invalid path")
        return pjoin(pptx_dir, "slide_images", fname), "image/jpeg"
    if artifact_name.startswith("template_image/"):
        fname = artifact_name.split("/", 1)[1]
        if ".." in fname or "/" in fname:
            raise HTTPException(status_code=400, detail="Invalid path")
        return pjoin(pptx_dir, "template_images", fname), "image/jpeg"
    if artifact_name.startswith("pdf_image/"):
        fname = artifact_name.split("/", 1)[1]
        if ".." in fname or "/" in fname:
            raise HTTPException(status_code=400, detail="Invalid path")
        return pjoin(pdf_dir, fname), "image/jpeg"

    raise HTTPException(status_code=404, detail=f"Unknown artifact: {artifact_name}")


@app.post("/api/upload")
async def create_task(
    pptxFile: UploadFile = File(None),
    pdfFile: UploadFile = File(None),
    topic: str = Form(None),
    numberOfPages: int = Form(...),
    generationMode: str = Form("auto"),
    useDefaultPptx: bool = Form(False),
):
    if generationMode not in ("auto", "ask"):
        raise HTTPException(status_code=400, detail="generationMode must be auto or ask")
    task_id = datetime.now().strftime("20%y-%m-%d") + "/" + str(uuid.uuid4())
    logger.info(f"task created: {task_id}")
    os.makedirs(pjoin(RUNS_DIR, task_id))
    task = {
        "numberOfPages": numberOfPages,
        "generationMode": generationMode,
    }
    if pptxFile is not None:
        pptx_blob = await pptxFile.read()
        pptx_md5 = hashlib.md5(pptx_blob).hexdigest()
        task["pptx"] = pptx_md5
        pptx_dir = pjoin(RUNS_DIR, "pptx", pptx_md5)
        if not os.path.exists(pptx_dir):
            os.makedirs(pptx_dir, exist_ok=True)
            with open(pjoin(pptx_dir, "source.pptx"), "wb") as f:
                f.write(pptx_blob)
    elif useDefaultPptx:
        default_path = pjoin(RUNS_DIR, "pptx", "default_template", "source.pptx")
        if not os.path.exists(default_path):
            raise HTTPException(status_code=404, detail="默认模板不存在，请上传参考PPT")
        task["pptx"] = "default_template"
    else:
        raise HTTPException(status_code=400, detail="请上传参考PPT或使用默认模板")
    if pdfFile is not None:
        pdf_blob = await pdfFile.read()
        pdf_md5 = hashlib.md5(pdf_blob).hexdigest()
        task["pdf"] = pdf_md5
        pdf_dir = pjoin(RUNS_DIR, "pdf", pdf_md5)
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir, exist_ok=True)
            with open(pjoin(pdf_dir, "source.pdf"), "wb") as f:
                f.write(pdf_blob)
    if topic is not None:
        task["pdf"] = topic
    progress_store[task_id] = task
    asyncio.create_task(ppt_gen(task_id))
    return {"task_id": task_api_id(task_id)}


@app.post("/api/ppt-preview")
async def create_ppt_preview(
    pptxFile: UploadFile = File(None),
    use_default: bool = Form(False),
):
    if use_default:
        preview_id = "default_template"
        run_dir = pjoin(RUNS_DIR, "pptx", preview_id)
        source_path = pjoin(run_dir, "source.pptx")
        if not os.path.exists(source_path):
            raise HTTPException(status_code=404, detail="默认模板不存在，请上传参考PPT")
    elif pptxFile is not None:
        blob = await pptxFile.read()
        preview_id = hashlib.md5(blob).hexdigest()
        run_dir = pjoin(RUNS_DIR, "pptx", preview_id)
        source_path = pjoin(run_dir, "source.pptx")
        if not os.path.exists(source_path):
            os.makedirs(run_dir, exist_ok=True)
            with open(source_path, "wb") as f:
                f.write(blob)
    else:
        raise HTTPException(status_code=400, detail="请上传参考PPT或选择默认模板")

    cfg = Config(run_dir)
    slide_dir = pjoin(cfg.RUN_DIR, "slide_images")
    presentation = await asyncio.to_thread(Presentation.from_file, source_path, cfg)
    if not os.path.isdir(slide_dir) or len(list_images_in_dir(slide_dir)) != len(presentation):
        await ppt_to_images_async(source_path, slide_dir)

    return {
        "preview_id": preview_id,
        "total_slides": len(presentation),
    }


@app.get("/api/ppt-preview/default-availability")
async def get_default_template_availability():
    default_path = pjoin(RUNS_DIR, "pptx", "default_template", "source.pptx")
    if os.path.exists(default_path):
        return {"available": True, "template_name": os.path.basename(default_path)}
    return {
        "available": False,
        "template_name": None,
        "reason": "missing_default_template",
    }


@app.get("/api/ppt-preview/{preview_id}/images")
async def get_ppt_preview_images(preview_id: str):
    preview_id = normalize_preview_id(preview_id)
    slide_dir = preview_slide_dir(preview_id)
    if not os.path.isdir(slide_dir):
        raise HTTPException(status_code=404, detail="预览不存在，请先生成预览")
    files = list_images_in_dir(slide_dir)
    return {
        "images": [
            {
                "name": f,
                "url": f"/api/ppt-preview/{preview_id}/image/{f}",
            }
            for f in files
        ]
    }


@app.get("/api/ppt-preview/{preview_id}/image/{fname:path}")
async def get_ppt_preview_image(preview_id: str, fname: str):
    preview_id = normalize_preview_id(preview_id)
    if ".." in fname or "/" in fname or "\\" in fname:
        raise HTTPException(status_code=400, detail="Invalid image path")
    path = pjoin(preview_slide_dir(preview_id), fname)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Preview image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.websocket("/wsapi/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    task_id = normalize_task_id(task_id)
    task_dir = pjoin(RUNS_DIR, task_id)
    if task_id not in progress_store and not os.path.exists(pjoin(task_dir, "task.json")):
        raise HTTPException(status_code=404, detail="Task not found")
    await websocket.accept()
    active_connections[task_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("websocket disconnected: %s", task_id)
        active_connections.pop(task_id, None)


@app.get("/api/task/{task_id}/pipeline")
async def get_pipeline_state(task_id: str):
    task_id = normalize_task_id(task_id)
    path = pipeline_state_path(task_id)
    if not os.path.exists(path):
        return JSONResponse(
            {
                "task_id": task_api_id(task_id),
                "generation_mode": "auto",
                "awaiting_human": None,
                "stages": {
                    s["id"]: {
                        "id": s["id"],
                        "label": s["label"],
                        "inputs": s["inputs"],
                        "outputs": s["outputs"],
                        "status": "pending",
                    }
                    for s in PIPELINE_STAGES
                },
            }
        )
    return json.load(open(path))


@app.get("/api/task/{task_id}/human-review")
async def get_human_review(task_id: str):
    task_id = normalize_task_id(task_id)
    path = human_review_path(task_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Human review not found")
    return json.load(open(path))


@app.post("/api/task/{task_id}/human-review/outline")
async def submit_outline_review(task_id: str, request: Request):
    task_id = normalize_task_id(task_id)
    path = human_review_path(task_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Human review not found")

    review_data = json.load(open(path))
    if review_data.get("status") != "waiting":
        raise HTTPException(status_code=409, detail="Human review is not waiting")

    body = await request.json()
    edited_outline = normalize_outline_edits(
        body.get("outline"),
        len(review_data.get("outline", [])),
    )

    future = human_review_futures.get(task_id)
    if future is None or future.done():
        raise HTTPException(
            status_code=409,
            detail="任务当前无法继续，请重新生成",
        )

    review_data["status"] = "confirmed"
    review_data["outline"] = edited_outline
    review_data["updated_at"] = time.time()
    json.dump(review_data, open(path, "w"), ensure_ascii=False, indent=2)

    future.set_result(edited_outline)
    return {"ok": True, "outline": edited_outline}


@app.get("/api/task/{task_id}/artifact/{artifact_name:path}")
async def get_artifact(task_id: str, artifact_name: str):
    task_id = normalize_task_id(task_id)
    tid = task_api_id(task_id)
    task = load_task_config(task_id)
    pptx_dir = pjoin(RUNS_DIR, "pptx", task["pptx"])
    pdf_dir = pjoin(RUNS_DIR, "pdf", task["pdf"])
    task_dir = pjoin(RUNS_DIR, task_id)

    if artifact_name == "slide_images":
        files = list_images_in_dir(pjoin(pptx_dir, "slide_images"))
        return {
            "images": [
                {
                    "name": f,
                    "url": f"/api/task/{tid}/artifact/slide_image/{f}",
                }
                for f in files
            ]
        }
    if artifact_name == "template_images":
        files = list_images_in_dir(pjoin(pptx_dir, "template_images"))
        return {
            "images": [
                {
                    "name": f,
                    "url": f"/api/task/{tid}/artifact/template_image/{f}",
                }
                for f in files
            ]
        }
    if artifact_name == "pdf_images":
        files = [
            f
            for f in os.listdir(pdf_dir)
            if is_image_path(pjoin(pdf_dir, f))
        ] if os.path.isdir(pdf_dir) else []
        return {
            "images": [
                {
                    "name": f,
                    "url": f"/api/task/{tid}/artifact/pdf_image/{f}",
                }
                for f in sorted(files)
            ]
        }
    if artifact_name == "slide_gen_status":
        state_path = pipeline_state_path(task_id)
        if os.path.exists(state_path):
            state = json.load(open(state_path))
            return state.get("slide_gen", {"slides": [], "completed": 0, "total": 0})
        return {"slides": [], "completed": 0, "total": 0}

    file_path, media_type = resolve_artifact_path(task_id, artifact_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    if media_type == "application/json":
        return json.load(open(file_path))
    if media_type == "text/markdown":
        content = open(file_path).read()
        truncated = len(content) > 8192
        if truncated:
            content = content[:8192] + "\n\n...(truncated)"
        return PlainTextResponse(content)
    if media_type == "application/pptx":
        return FileResponse(
            file_path,
            media_type=media_type,
            headers={"Content-Disposition": "attachment; filename=pptagent.pptx"},
        )
    return FileResponse(file_path, media_type=media_type)


@app.get("/api/download")
async def download(task_id: str):
    task_id = normalize_task_id(task_id)
    file_path, _ = resolve_artifact_path(task_id, "final")
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            media_type="application/pptx",
            headers={"Content-Disposition": "attachment; filename=pptagent.pptx"},
        )
    raise HTTPException(status_code=404, detail="Task not finished yet")


@app.post("/api/task/{task_id}/final-preview")
async def create_final_ppt_preview(task_id: str):
    task_id = normalize_task_id(task_id)
    file_path, _ = resolve_artifact_path(task_id, "final")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="任务尚未完成，无法预览")

    preview_id = f"final_{task_api_id(task_id).replace('|', '_')}"
    run_dir = preview_dir(preview_id)
    os.makedirs(run_dir, exist_ok=True)
    cfg = Config(run_dir)
    slide_dir = pjoin(cfg.RUN_DIR, "slide_images")
    presentation = await asyncio.to_thread(Presentation.from_file, file_path, cfg)
    if not os.path.isdir(slide_dir) or len(list_images_in_dir(slide_dir)) != len(presentation):
        await ppt_to_images_async(file_path, slide_dir)

    return {
        "preview_id": preview_id,
        "total_slides": len(presentation),
    }


@app.post("/api/feedback")
async def feedback(request: Request):
    body = await request.json()
    feedback_text = body.get("feedback")
    task_id = body.get("task_id")
    os.makedirs(pjoin(RUNS_DIR, "feedback"), exist_ok=True)
    with open(pjoin(RUNS_DIR, "feedback", f"{task_id}.txt"), "w") as f:
        f.write(feedback_text)
    return {"message": "Feedback submitted successfully"}


@app.get("/api/pipeline/stages")
async def get_pipeline_stages():
    return {"stages": PIPELINE_STAGES}


@app.get("/api/task/{task_id}/agent-traces")
async def list_agent_traces(task_id: str):
    task_id = normalize_task_id(task_id)
    trace_dir = agent_traces_dir(task_id)
    if not os.path.isdir(trace_dir):
        return {"traces": []}
    traces = sorted(
        f[:-5] for f in os.listdir(trace_dir) if f.endswith(".json")
    )
    return {"traces": traces}


@app.get("/api/task/{task_id}/agent-traces/{trace_name}")
async def get_agent_trace(task_id: str, trace_name: str):
    task_id = normalize_task_id(task_id)
    if ".." in trace_name or "/" in trace_name or "\\" in trace_name:
        raise HTTPException(status_code=400, detail="Invalid trace name")
    path = pjoin(agent_traces_dir(task_id), f"{trace_name}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Agent trace not found")
    data = json.load(open(path))
    return truncate_trace_value(data)


@app.get("/")
async def hello():
    return {"message": "Hello, World!"}


async def ppt_gen(task_id: str, rerun=False):
    if DEBUG:
        importlib.reload(induct)
        importlib.reload(pptgen)
    if rerun:
        task_id = normalize_task_id(task_id)
        active_connections[task_id] = None
        progress_store[task_id] = json.load(open(pjoin(RUNS_DIR, task_id, "task.json")))

    for _ in range(100):
        if task_id in active_connections:
            break
        await asyncio.sleep(0.02)
    else:
        progress_store.pop(task_id, None)
        return

    task = progress_store.pop(task_id)
    pptx_md5 = task["pptx"]
    pdf_md5 = task["pdf"]
    generation_config = Config(pjoin(RUNS_DIR, task_id))
    pptx_config = Config(pjoin(RUNS_DIR, "pptx", pptx_md5))
    parsedpdf_dir = pjoin(RUNS_DIR, "pdf", pdf_md5)
    ppt_image_folder = pjoin(pptx_config.RUN_DIR, "slide_images")

    generation_mode = task.get("generationMode", "auto")
    progress = ProgressManager(task_id, generation_config.RUN_DIR, generation_mode)

    try:
        # --- init ---
        await progress.report_stage_start("init")
        json.dump(task, open(pjoin(generation_config.RUN_DIR, "task.json"), "w"))
        await progress.report_stage_complete(
            "init",
            {
                "numberOfPages": task["numberOfPages"],
                "generationMode": task.get("generationMode", "auto"),
                "pptx": task["pptx"],
                "pdf": task["pdf"],
            },
        )

        # --- ppt_parse ---
        await progress.report_stage_start("ppt_parse")
        ppt_cached = (
            os.path.exists(ppt_image_folder)
            and os.path.exists(pjoin(pptx_config.RUN_DIR, "image_stats.json"))
        )
        presentation = await asyncio.to_thread(
            Presentation.from_file,
            pjoin(pptx_config.RUN_DIR, "source.pptx"),
            pptx_config,
        )
        if not os.path.exists(ppt_image_folder) or len(
            os.listdir(ppt_image_folder)
        ) != len(presentation):
            await ppt_to_images_async(
                pjoin(pptx_config.RUN_DIR, "source.pptx"), ppt_image_folder
            )
            for err_idx, _ in presentation.error_history:
                os.remove(pjoin(ppt_image_folder, f"slide_{err_idx:04d}.jpg"))
            for i, slide in enumerate(presentation.slides, 1):
                slide.slide_idx = i
                os.rename(
                    pjoin(ppt_image_folder, f"slide_{slide.real_idx:04d}.jpg"),
                    pjoin(ppt_image_folder, f"slide_{slide.slide_idx:04d}.jpg"),
                )

        labler = ImageLabler(presentation, pptx_config)
        if os.path.exists(pjoin(pptx_config.RUN_DIR, "image_stats.json")):
            image_stats = json.load(
                open(pjoin(pptx_config.RUN_DIR, "image_stats.json"))
            )
            labler.apply_stats(image_stats)
        else:
            await labler.caption_images_async(models.vision_model)
            json.dump(
                labler.image_stats,
                open(pjoin(pptx_config.RUN_DIR, "image_stats.json"), "w"),
                ensure_ascii=False,
                indent=4,
            )
        image_stats = json.load(open(pjoin(pptx_config.RUN_DIR, "image_stats.json")))
        await progress.report_stage_complete(
            "ppt_parse",
            {
                "slide_count": len(presentation),
                "image_count": len(image_stats),
            },
            cached=ppt_cached,
        )

        # --- pdf_parse ---
        await progress.report_stage_start("pdf_parse")
        pdf_cached = os.path.exists(pjoin(parsedpdf_dir, "source.md"))
        if not pdf_cached:
            text_content = await run_blocking_with_heartbeat(
                progress,
                "pdf_parse",
                parse_pdf,
                pjoin(RUNS_DIR, "pdf", pdf_md5, "source.pdf"),
                parsedpdf_dir,
                models.marker_model,
                message="marker-pdf 正在解析 PDF（CPU 占用较高，请耐心等待）",
            )
        else:
            text_content = open(pjoin(parsedpdf_dir, "source.md")).read()
        pdf_images = list_images_in_dir(parsedpdf_dir)
        await progress.report_stage_complete(
            "pdf_parse",
            {
                "markdown_chars": len(text_content),
                "extracted_images": len(pdf_images),
                "has_meta": os.path.exists(pjoin(parsedpdf_dir, "meta.json")),
            },
            cached=pdf_cached,
        )

        # --- doc_refine ---
        await progress.report_stage_start("doc_refine")
        doc_cached = os.path.exists(pjoin(parsedpdf_dir, "refined_doc.json"))
        if not doc_cached:
            source_doc, doc_extractor_history = await Document.from_markdown_async(
                text_content,
                models.language_model,
                models.vision_model,
                parsedpdf_dir,
            )
            json.dump(
                source_doc.to_dict(),
                open(pjoin(parsedpdf_dir, "refined_doc.json"), "w"),
                ensure_ascii=False,
                indent=4,
            )
            save_agent_trace(
                task_id,
                "doc_extractor",
                {"turns": doc_extractor_history},
            )
        else:
            source_doc = json.load(open(pjoin(parsedpdf_dir, "refined_doc.json")))
            source_doc = Document.from_dict(source_doc, parsedpdf_dir)
        refined = json.load(open(pjoin(parsedpdf_dir, "refined_doc.json")))
        section_count = len(refined.get("sections", []))
        await progress.report_stage_complete(
            "doc_refine",
            {"section_count": section_count},
            cached=doc_cached,
        )

        # --- template_prep + slide_induction ---
        induction_cached = os.path.exists(
            pjoin(pptx_config.RUN_DIR, "slide_induction.json")
        )
        template_cached = os.path.exists(
            pjoin(pptx_config.RUN_DIR, "template_images")
        ) and len(list_images_in_dir(pjoin(pptx_config.RUN_DIR, "template_images"))) > 0

        await progress.report_stage_start("template_prep")
        if not induction_cached:
            if not template_cached:
                deepcopy(presentation).save(
                    pjoin(pptx_config.RUN_DIR, "template.pptx"), layout_only=True
                )
                await ppt_to_images_async(
                    pjoin(pptx_config.RUN_DIR, "template.pptx"),
                    pjoin(pptx_config.RUN_DIR, "template_images"),
                )
        template_count = len(
            list_images_in_dir(pjoin(pptx_config.RUN_DIR, "template_images"))
        )
        await progress.report_stage_complete(
            "template_prep",
            {"template_image_count": template_count},
            cached=template_cached and induction_cached,
        )

        await progress.report_stage_start("slide_induction")
        if not induction_cached:
            slide_inducter = induct.SlideInducterAsync(
                presentation,
                ppt_image_folder,
                pjoin(pptx_config.RUN_DIR, "template_images"),
                pptx_config,
                models.image_model,
                models.language_model,
                models.vision_model,
            )
            layout_induction = await slide_inducter.layout_induct()
            slide_induction = await slide_inducter.content_induct(layout_induction)
            json.dump(
                slide_induction,
                open(pjoin(pptx_config.RUN_DIR, "slide_induction.json"), "w"),
                ensure_ascii=False,
                indent=4,
            )
            save_agent_trace(
                task_id,
                "schema_extractor",
                {"turns": slide_inducter.get_schema_extractor_history()},
            )
        else:
            slide_induction = json.load(
                open(pjoin(pptx_config.RUN_DIR, "slide_induction.json"))
            )
        functional_keys = slide_induction.get("functional_keys", [])
        layout_keys = [
            k for k in slide_induction if k != "functional_keys"
        ]
        await progress.report_stage_complete(
            "slide_induction",
            {
                "layout_count": len(layout_keys),
                "functional_keys": functional_keys,
            },
            cached=induction_cached,
        )

        # --- PPT Generation ---
        ppt_agent = pptgen.PPTAgentAsync(
            models.text_model,
            models.language_model,
            models.vision_model,
            error_exit=False,
            retry_times=5,
        )
        ppt_agent.set_reference(
            config=generation_config,
            slide_induction=deepcopy(slide_induction),
            presentation=presentation,
        )

        slide_gen_slides: list[dict] = []
        live_slide_traces: list[dict] = []

        async def on_pptgen_progress(event: str, data: dict):
            if event == "outline_done":
                outline_path = pjoin(generation_config.RUN_DIR, "outline.json")
                outline = data.get("outline", [])
                json.dump(
                    outline,
                    open(outline_path, "w"),
                    ensure_ascii=False,
                    indent=2,
                )
                planner_turns = [
                    turn.to_dict()
                    for turn in ppt_agent.staffs["planner"].history
                ]
                save_agent_trace(task_id, "planner", {"turns": planner_turns})
                await progress.report_stage_start("outline")
                await progress.report_subprogress(
                    "outline",
                    {
                        "message": "大纲已生成",
                        "agent_trace": {"turns": planner_turns},
                    },
                )
                if generation_mode == "ask":
                    outline = await wait_for_outline_review(progress, task_id, outline)
                    json.dump(
                        outline,
                        open(outline_path, "w"),
                        ensure_ascii=False,
                        indent=2,
                    )
                await progress.report_stage_complete(
                    "outline",
                    {
                        "total_slides": len(outline),
                        "outline_preview": outline[:5],
                    },
                )
                await progress.report_stage_start("slide_gen")
                progress.state["slide_gen"] = {
                    "slides": [],
                    "completed": 0,
                    "total": len(outline),
                }
                save_pipeline_state(task_id, progress.state)
                return outline
            elif event == "agent_turn":
                live_slide_traces.append(data)
                live_slide_traces.sort(key=lambda x: x.get("index", 0))
                await progress.report_subprogress(
                    "slide_gen",
                    {
                        "agent_trace": data,
                        "live_traces": live_slide_traces,
                    },
                )
            elif event == "slide_done":
                slide_gen_slides.append(
                    {
                        "index": data["index"],
                        "purpose": data["purpose"],
                        "section": data["section"],
                        "success": data["success"],
                        "error": data.get("error"),
                    }
                )
                slide_gen_slides.sort(key=lambda x: x["index"])
                await progress.report_subprogress(
                    "slide_gen",
                    {
                        "slides": slide_gen_slides,
                        "completed": data["completed"],
                        "total": data["total"],
                        "current_purpose": data["purpose"],
                        "elapsed_ms": data.get("elapsed_ms", 0),
                    },
                )

        prs, gen_history = await ppt_agent.generate_pres(
            source_doc=source_doc,
            num_slides=task["numberOfPages"],
            on_progress=on_pptgen_progress,
        )
        save_agent_trace(task_id, "slide_gen", gen_history)
        success_count = sum(1 for s in slide_gen_slides if s.get("success"))
        await progress.report_stage_complete(
            "slide_gen",
            {
                "completed": len(slide_gen_slides),
                "success_count": success_count,
                "total": len(slide_gen_slides),
            },
        )

        if prs is None:
            raise RuntimeError("PPT generation failed: no slides produced")
        prs.save(pjoin(generation_config.RUN_DIR, "final.pptx"))
        logger.info(f"{task_id}: generation finished")

        await progress.report_stage_complete(
            "done",
            {
                "output_file": "final.pptx",
                "total_elapsed_ms": progress._elapsed_ms(),
            },
        )
    except Exception as e:
        await progress.fail_stage(str(e))
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn

    ip = "0.0.0.0"
    uvicorn.run(app, host=ip, port=9297)
