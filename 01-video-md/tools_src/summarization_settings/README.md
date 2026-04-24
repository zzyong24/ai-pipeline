# summarization-settings

> 获取/修改 msg-collect 的 LLM 总结配置（mode、chunk 参数、enable_summarization 等）。

## 验收标准

- ✅ 单一职责：只读写 summarization 配置
- ✅ 输入输出明确：`get_settings()` / `update_settings(mode=, enable_summarization=, ...)`
- ✅ 可 CLI：`summarization-settings get | set --enable-summarization true`
- ✅ 可 import：`from summarization_settings import get_settings, update_settings`
- ✅ 可 n8n 编排：n8n Execute Command 调用 `_wrappers/summarization_settings.py`

## CLI 用法

```bash
# 获取当前配置
summarization-settings get

# 修改配置
summarization-settings set --enable-summarization true --mode agent
```

## Python API

```python
from summarization_settings import get_settings, update_settings

# 读取
cfg = get_settings()
print(cfg["enable_summarization"], cfg["mode"])

# 修改
update_settings(enable_summarization=True, mode="agent")
```

## 依赖

- `requests`（`pip install requests`）
- msg-collect 服务需在 `http://127.0.0.1:8000` 运行

## 环境变量

```bash
export MSG_COLLECT_BASE=http://127.0.0.1:8000
```
