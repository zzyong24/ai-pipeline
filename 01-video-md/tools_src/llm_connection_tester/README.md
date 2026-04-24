# llm-connection-tester

> 测试 MiniMax LLM 连接是否可用（调用 msg-collect `/llm/test`）。

## 验收标准

- ✅ 单一职责：只测 LLM 连通性
- ✅ 输入输出明确：`test_connection(provider) → dict`
- ✅ 可 CLI：`llm-connection-test`
- ✅ 可 import：`from llm_connection_tester import test_connection`
- ✅ 可 n8n 编排：工作流前置检查

## CLI 用法

```bash
llm-connection-test
# 输出 {"status": "ok", "message": "...", "response": "OK"}
# exit 0 表示成功
```

## Python API

```python
from llm_connection_tester import test_connection
result = test_connection()
if result["status"] == "ok":
    print("LLM 可用")
```

## 依赖

- `requests`
- msg-collect 服务

## 环境变量

```bash
export MSG_COLLECT_BASE=http://127.0.0.1:8000
```
