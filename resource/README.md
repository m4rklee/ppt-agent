# 资源文件说明

本目录存放 README 引用的演示视频、工作流配图与生成案例截图。

## 文件清单

| 路径 | 用途 | 建议规格 |
|------|------|----------|
| `demo.mp4` | README「演示视频」区块 | 30–90 秒，展示上传 → 生成 → 预览流程；也可用 `demo.gif` |
| `fig2.jpg` | PPTAgent 工作流 / UI 流水线截图 | 宽 1200px 左右，JPG 或 PNG |
| `fig3.jpg` | PPTEval 评估流程示意图（可选） | 宽 800–1200px |
| `cases/case01/0001.jpg` … | 案例一各页缩略图 | 单张宽 400–800px，按页码递增命名 |

## 案例图片命名规范

```
cases/
  case01/
    0001.jpg   # 第 1 页
    0002.jpg   # 第 2 页
    ...
  case02/      # 可选第二个案例
    0001.jpg
    ...
```

将 PPTX 导出为图片，或从 Web UI 完成页预览截图，按上述命名放入对应目录后执行：

```bash
git add resource/
git commit -m "docs: add demo and case study assets"
git push origin main
```

## 注意事项

- `resource/exemplars/` 已在 `.gitignore` 中排除，勿将大体积示例数据放在该目录外未忽略的临时路径
- 提交前确认图片中不含 API Key、个人文档等敏感信息
