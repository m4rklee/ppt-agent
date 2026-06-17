# PPT Agent

> 一个能够自动生成PPT的Agent.

用户上传 PDF 文档与参考 PPT，系统自动完成文档解析、大纲规划、内容组织、版式选择、页面编辑和 PPT 生成。

## 项目功能

- **PDF转PPT**: 从输入文档自动生成结构化演示文稿。
- **PPT模版驱动**: 支持自定义PPT模版，能够生成个性化PPT。
- **多Agent集成**: doc_extractor、schema_extractor、planner、content_organizer、layout_selector、editor、coder 分工协作。
- **Human-in-the-loop**: 支持 `auto` 全自动和 `ask` 大纲确认模式。

## 项目演示

### 主页

### PPT生成流程

### 大纲编辑

### 生成效果

案例截图可放在：

```text
resource/cases/
```

## 项目流程

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
## 技术栈

- **Backend**: Python 3.11, FastAPI, Uvicorn, PPTAgent core
- **LLM**: OpenAI-compatible API
- **Frontend**: Vue 3, Vue Router, Axios
- **Document/PPT**: marker-pdf, python-pptx fork, Pillow, OpenCV
- **Tooling**: Conda, npm, shell scripts

## 快速开始

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

## 项目结构

```text
pptagent/                # PPT生成相关的核心代码
pptagent_ui/             # 前端页面
docker/                  # Docker相关
DOC.md                   # 用法介绍
```

