# PPT Agent Web

> An automated presentation generation web application built on top of PPTAgent.

PPT Agent Web 是基于 [PPTAgent](https://github.com/icip-cas/PPTAgent) 的应用层 fork。用户上传 PDF 文档与参考 PPT，系统自动完成文档解析、大纲规划、内容组织、版式选择、页面编辑和 PPTX 生成，并提供 Vue Web UI、Pipeline 可视化、Agent Trace、Human-in-the-loop 大纲确认和结果预览下载。

本仓库保留上游论文与核心生成链路，同时补充了面向实际使用的 Web 产品体验。

## Links

- Paper: [PPTAgent: Generating and Evaluating Presentations Beyond Text-to-Slides](https://arxiv.org/abs/2501.03936)
- Upstream: [icip-cas/PPTAgent](https://github.com/icip-cas/PPTAgent)
- Local docs: [DOC.md](DOC.md)

## Highlights

- **PDF-to-PPT workflow**: 从输入文档自动生成结构化演示文稿。
- **Reference-driven styling**: 深拷贝参考 PPT 模板，通过编辑指令替换文本和图片，保留版式风格。
- **Multi-agent pipeline**: doc_extractor、schema_extractor、planner、content_organizer、layout_selector、editor、coder 分工协作。
- **Human-in-the-loop**: 支持 `auto` 全自动和 `ask` 大纲确认模式。
- **Web observability**: Vue UI 展示 pipeline 时间线、阶段状态、中间产物和 Agent Trace。
- **Preview and download**: 支持上传模板预览、最终 PPT 缩略图预览和 PPTX 下载。

## Demo

演示视频可放在：

```text
resource/demo.mp4
```

案例截图可放在：

```text
resource/cases/
```

若你在 GitHub Release 或 issue 中上传了录屏，可将链接补充到本节。

## Architecture

```text
Vue Web UI
    |
    v
pptagent_ui/backend.py
    |
    v
PPTAgent pipeline
    |
    +--> document extraction
    +--> schema extraction
    +--> planning
    +--> content organization
    +--> layout selection
    +--> edit instruction generation
    +--> code execution over PPT template
    |
    v
Generated PPTX
```

## Features

| Module | Description |
|---|---|
| **Document Understanding** | 解析 PDF 内容，提取文档结构和关键信息。 |
| **Outline Planning** | 根据文档目的和章节规划演示文稿结构。 |
| **Template Reuse** | 参考 PPT 驱动版式和视觉风格。 |
| **Slide Editing** | 生成编辑指令并通过 CodeExecutor 修改 PPTX。 |
| **Pipeline UI** | 在 Web 页面展示阶段状态、耗时和生成进度。 |
| **HITL Mode** | 大纲生成后允许用户调整 purpose/section 再继续。 |

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn, PPTAgent core
- **LLM**: OpenAI-compatible API
- **Frontend**: Vue 3, Vue Router, Axios
- **Document/PPT**: marker-pdf, python-pptx fork, Pillow, OpenCV
- **Tooling**: Conda, npm, shell scripts

## Quick Start

```bash
git clone https://github.com/m4rklee/ppt-agent.git
cd ppt-agent
cp .env.example .env
```

编辑 `.env`，填入模型 API Key。然后启动：

```bash
./scripts/run_local.sh all
```

服务默认地址：

```text
Backend:  http://0.0.0.0:9297
Frontend: http://localhost:8088
```

也可以分别启动：

```bash
./scripts/run_local.sh backend
./scripts/run_local.sh frontend
```

## Usage

1. 打开 Web UI。
2. 上传 PDF 文档。
3. 上传参考 PPTX，或使用内置默认模板。
4. 选择 `auto` 或 `ask` 模式。
5. 等待 pipeline 执行，查看阶段详情和 Agent Trace。
6. 预览并下载生成的 PPTX。

更多说明见 [DOC.md](DOC.md)。

## Project Structure

```text
pptagent/                # Upstream PPT generation core
pptagent_ui/             # Vue UI and Python backend entry
pptx/                    # Bundled PPT manipulation package
resource/                # Demo assets, templates and cases
scripts/                 # Local startup and smoke-test scripts
docker/                  # Docker-related files
DOC.md                   # Usage and implementation docs
```

## Notes

- 本仓库是应用层 fork，核心研究工作和论文归属于上游 PPTAgent。
- 本地运行需要可用的 LLM API Key，复杂文档生成质量取决于模型能力和参考模板质量。
- PPT 生成过程中会创建中间文件，建议在独立工作目录中运行。

## Roadmap

- Add hosted demo screenshots and generated PPT examples.
- Improve pipeline error recovery.
- Add template gallery and default style presets.
- Add evaluation examples for generated slides.

## Citation

If you use the upstream PPTAgent research work, please cite the original paper and repository linked above.
