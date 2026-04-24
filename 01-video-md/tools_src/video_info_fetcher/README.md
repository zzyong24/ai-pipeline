# video-info-fetcher

> 接收 B 站视频 URL，返回是否多 P 及各分 P 的标题/索引。

## 验收标准

- ✅ 单一职责：只查询 B 站视频元信息
- ✅ 输入输出明确：`fetch_video_info(url) → dict`
- ✅ 可 CLI：`video-info-fetch <url>`
- ✅ 可 import：`from video_info_fetcher import fetch_video_info`
- ✅ 可 n8n 编排：n8n Execute Command 调用 `_wrappers/video_info_fetch.py`

## CLI 用法

```bash
video-info-fetch "https://www.bilibili.com/video/BV1nFDSBPEWP"
video-info-fetch "https://b23.tv/xxx"
```

## Python API

```python
from video_info_fetcher import fetch_video_info

result = fetch_video_info("https://www.bilibili.com/video/BV1xxx")
# result: {
#   "is_multi_part": bool,
#   "title": str,
#   "bvid": str,
#   "duration": int,
#   "parts": [{"index": 0, "cid": int, "title": str, "duration": int}, ...] | None
# }
```

## n8n 编排

```bash
python3 ~/Workbase/tools/src/_wrappers/video_info_fetch.py \
  --url "{{ $json.body.url }}"
```

## 依赖

- `bilibili_api`（已装在 msg-collect venv）
