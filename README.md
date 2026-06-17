# PPT生成助手：基于 PPTAgent 的自动化演示文稿 Web 应用

<p align="center">
  📄 <a href="https://arxiv.org/abs/2501.03936" target="_blank">上游论文</a> &nbsp; | &nbsp;
  🔗 <a href="https://github.com/icip-cas/PPTAgent" target="_blank">上游仓库</a> &nbsp; | &nbsp;
  📝 <a href="./DOC.md" target="_blank">文档</a> &nbsp; | &nbsp;
  🚀 <a href="#快速开始" target="_blank">快速开始</a> &nbsp; | &nbsp;
  🙏 <a href="#citation" target="_blank">引用</a>
</p>

本项目是 [PPTAgent](https://github.com/icip-cas/PPTAgent) 的应用层 fork。上传 PDF 文档与参考 PPT（或使用内置默认模板），系统即可自动生成结构清晰、版式统一的演示文稿。在此基础上，我们提供 **Vue Web UI**：全流程 Pipeline 可视化、Agent 调用追踪、Human-in-the-loop 大纲确认，以及生成前后的 PPT 预览与下载。

> [!TIP]
> 本地快速启动：复制 `.env.example` 为 `.env` 并填入 API Key，然后执行 `./scripts/run_local.sh all`。详见下方 [快速开始](#快速开始)。

## 演示视频

<!-- 将录屏放入 resource/demo.mp4 后取消下行注释，或改用 demo.gif -->
<!-- https://github.com/user-attachments/assets/... -->

演示视频文件：`resource/demo.mp4`（请将你本地的操作录屏放入该路径后提交）

## 核心特性

- **参考 PPT 驱动生成**：深拷贝参考幻灯片，通过 LLM 生成编辑指令序列，由 CodeExecutor 执行文本与图片替换，保留原模板版式风格
- **Web 全流程可视化**：Pipeline 时间线展示各阶段状态与耗时；阶段详情面板展示中间产物、Agent Trace 与逐页生成进度
- **Human-in-the-loop**：支持 `auto`（全自动）与 `ask`（大纲生成后暂停，用户可编辑 purpose/section 再继续）两种模式
- **默认内置模板**：无需上传参考 PPTX 即可开始生成，降低使用门槛
- **PPT 预览**：上传页可预览参考模板；完成页支持最终 PPTX 缩略图预览与全屏 lightbox 浏览
- **多 Agent 协作**：doc_extractor → schema_extractor → planner → content_organizer / layout_selector / editor / coder 分工完成文档理解与幻灯片生成

## 案例展示

#### 案例一：PDF 自动生成演示文稿

<!-- 将生成结果截图放入 resource/cases/case01/，命名为 0001.jpg、0002.jpg … -->

<div style="display: flex; flex-wrap: wrap; gap: 10px;">

  <img src="resource/cases/case01/0001.jpg" alt="案例1-第1页" width="200"/>

  <img src="resource/cases/case01/0002.jpg" alt="案例1-第2页" width="200"/>

  <img src="resource/cases/case01/0003.jpg" alt="案例1-第3页" width="200"/>

  <img src="resource/cases/case01/0004.jpg" alt="案例1-第4页" width="200"/>

  <img src="resource/cases/case01/0005.jpg" alt="案例1-第5页" width="200"/>

  <img src="resource/cases/case01/0006.jpg" alt="案例1-第6页" width="200"/>

</div>

> 图片占位：请将你的生成案例截图放入 `resource/cases/case01/` 目录。命名规范见 [`resource/README.md`](resource/README.md)。

## PPTAgent 技术说明

PPTAgent 采用两阶段流程，本 Web 应用在 [`pptagent_ui/backend.py`](pptagent_ui/backend.py) 中将其编排为可观测的流水线：

### 1. 分析阶段

从参考 PPT 中学习版式与内容模式（[`pptagent/induct.py`](pptagent/induct.py)）：

- 使用 ViT（`google/vit-base-patch16-224-in21k`）提取页面图像 embedding，进行版式聚类
- 将幻灯片转为 HTML 中间表示，由 LLM（`schema_extractor`）提取每类版式的结构化 schema

### 2. 生成阶段

基于源文档与模板 schema 逐页生成（[`pptagent/pptgen.py`](pptagent/pptgen.py)）：

- **planner** 生成演示大纲
- **content_organizer** 组织文档要点
- **layout_selector** 选择版式模板
- **editor** 生成符合 schema 的内容
- **coder** 输出 API 编辑指令，**CodeExecutor** 在参考页副本上执行修改

### 3. Web 流水线阶段

```
任务初始化 → 参考 PPT 解析 → PDF 解析 → 文档结构化 → 版式模板图
→ 模板分析 → 大纲生成 → 逐页生成 → 完成
```

对应阶段 ID：`init` → `ppt_parse` → `pdf_parse` → `doc_refine` → `template_prep` → `slide_induction` → `outline` → `slide_gen` → `done`

![PPTAgent 工作流](resource/fig2.jpg)

> 工作流配图：请将 UI 流水线截图或架构图放入 `resource/fig2.jpg`。

## 快速开始

### 环境要求

- Python 3.11（推荐 conda 环境 `pptagent`）
- Node.js（用于前端 `pptagent_ui`）
- OpenAI 兼容 API（语言模型 + 视觉模型）

### 配置与启动

```bash
# 1. 克隆仓库
git clone https://github.com/m4rklee/ppt-agent.git
cd ppt-agent

# 2. 配置 API
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY、API_BASE、LANGUAGE_MODEL、VISION_MODEL 等

# 3. 安装 Python 依赖（参见 DOC.md / requirements.txt）
pip install -r requirements.txt

# 4. 安装前端依赖
cd pptagent_ui && npm install && cd ..

# 5. 启动后端 + 前端
./scripts/run_local.sh all
# 后端 http://127.0.0.1:9297  前端 http://localhost:8088
```

也可分别启动：

```bash
./scripts/run_local.sh backend   # 仅后端
./scripts/run_local.sh frontend  # 仅前端
```

## PPTEval 评估体系

PPTEval 从三个维度对演示文稿进行自动评分（[`pptagent/ppteval.py`](pptagent/ppteval.py)）：

- **内容（Content）**：幻灯片信息准确性与相关性
- **设计（Design）**：视觉美观度与风格一致性
- **连贯性（Coherence）**：整体逻辑与叙事流畅度

> **说明**：PPTEval 当前以离线脚本形式提供，Web UI 生成流程结束后**不会自动调用评估**。如需评分，可单独运行 `ppteval.py`。

<p align="center">
<img src="resource/fig3.jpg" alt="PPTEval 工作流" style="width:70%;"/>
</p>

> PPTEval 配图（可选）：放入 `resource/fig3.jpg`。

## Citation

本仓库为 PPTAgent 的应用层增强 fork，核心算法与学术成果请参阅原论文与 [icip-cas/PPTAgent](https://github.com/icip-cas/PPTAgent)。若本项目对你有帮助，引用上游工作时请使用：

```bibtex
@article{zheng2025pptagent,
  title={PPTAgent: Generating and Evaluating Presentations Beyond Text-to-Slides},
  author={Zheng, Hao and Guan, Xinyan and Kong, Hao and Zheng, Jia and Zhou, Weixiang and Lin, Hongyu and Lu, Yaojie and He, Ben and Han, Xianpei and Sun, Le},
  journal={arXiv preprint arXiv:2501.03936},
  year={2025}
}
```

[![Star History Chart](https://api.star-history.com/svg?repos=m4rklee/ppt-agent&type=Date)](https://star-history.com/#m4rklee/ppt-agent&Date)
