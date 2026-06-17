#!/usr/bin/env bash
# 自动化试跑：上传示例 PDF，等待生成，下载 PPT
# 用法: ./scripts/smoke_test.sh [页数，默认 3]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PAGES="${1:-3}"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate pptagent

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

python <<PY
import asyncio, json
from pathlib import Path
import httpx, websockets

ROOT = Path("$ROOT_DIR")
PDF = ROOT / "runs/pdf/c2dded76b30a6961129020bad17b3ccb/source.pdf"
BASE = "http://127.0.0.1:9297"
PAGES = int("$PAGES")

async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        with PDF.open("rb") as f:
            resp = await client.post(
                f"{BASE}/api/upload",
                data={"numberOfPages": str(PAGES)},
                files={"pdfFile": (PDF.name, f, "application/pdf")},
            )
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        print(f"task_id={task_id}")

    ws_url = f"ws://127.0.0.1:9297/wsapi/{task_id}"
    async with websockets.connect(ws_url, open_timeout=30) as ws:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=3600)
            data = json.loads(msg)
            print(f"progress={data.get('progress')} status={data.get('status')}", flush=True)
            if data.get("progress", 0) >= 100:
                if "Error" in data.get("status", ""):
                    raise RuntimeError(data["status"])
                break

    async with httpx.AsyncClient(timeout=120.0) as client:
        dl = await client.get(f"{BASE}/api/download", params={"task_id": task_id})
        dl.raise_for_status()
        out = ROOT / "runs" / "smoke_test_output.pptx"
        out.write_bytes(dl.content)
        print(f"SUCCESS: {out} ({len(dl.content)} bytes)")

asyncio.run(main())
PY
