# whisper-summarizer

**单一职责：SRT/TXT 字幕文件 → LLM 结构化总结**

## 安装

```bash
pip install -e ~/Workbase/tools
```

## CLI

```bash
whisper-summarize ./demo.srt -o ./AI总结.md
whisper-summarizer ./demo.txt -o ./AI总结.md
```

## Python 调用

```python
from whisper_summarizer import summarize

result = summarize("./demo.srt", output_path="./AI总结.md")
# result = {"summary": "...", "output_path": "..."}
```

## 依赖

- `requests`（直接调用 MiniMax API，无需 litellm）
- `MINIMAX_CN_API_KEY` 环境变量

## 工作流编排

适合 n8n 工作流：
1. 上游：video-transcriber 生成字幕
2. 本工具：whisper-summarize 生成结构化总结
3. 下游：保存到 Obsidian / 飞书文档 / 内容队列

## 设计原则

- 单一职责：只做总结，不管转录和存储
- 输入：SRT 或 TXT 文件
- 输出：Markdown 格式结构化总结
- 直接调用 MiniMax API，不走 litellm 中间层
