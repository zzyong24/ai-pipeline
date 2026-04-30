# 测试规范（Testing Spec）

> 本规范适用于所有使用 AIES 管理的项目。
> **强制**：每个任务的 PRD 必须包含配套的 `acceptance.md`（验收与测试文件），没有 `acceptance.md` 的任务不得进入 implement 阶段。

---

## 一、核心原则

1. **需求驱动**：测试从用户需求出发，不是从代码出发
2. **两层覆盖**：单元测试（Unit）+ 端到端功能测试（E2E），缺一不可
3. **确定性优先**：测试必须可重复执行，外部依赖全部 Mock
4. **失败即阻断**：任何测试失败，任务不得标记为 `done`

---

## 二、`acceptance.md` 文件规范（强制）

每个任务目录下必须有 `acceptance.md`，与 `prd.md` 并列：

```
.aies/tasks/{slug}/
├── task.json
├── prd.md          ← 需求描述
└── acceptance.md   ← 验收与测试（本规范约束的文件）
```

### 2.1 文件结构模板

```markdown
# 验收与测试：{任务标题}

> 任务 ID：{slug}
> 对应 PRD：prd.md

---

## 一、验收场景（从用户需求出发）

| # | 用户场景 | 输入 | 期望输出 | 优先级 |
|---|---------|------|---------|-------|
| AC-01 | 用户做了 X | ... | 系统返回 Y | P0 |
| AC-02 | 用户在边界条件下做了 X | ... | 系统安全处理 | P1 |

---

## 二、单元测试矩阵

| 测试用例 | 被测函数/类 | 输入 | 期望输出 | Mock 什么 |
|---------|-----------|------|---------|---------|
| UT-01 | foo() | 正常参数 | 期望值 | 外部 API |
| UT-02 | foo() | 空输入 | 抛 ValueError | 无 |
| UT-03 | foo() | 超时 | 返回 fallback | time.sleep |

**测试文件位置**：`tests/unit/test_{module}.py`

---

## 三、端到端测试（E2E）

### 3.1 Happy Path（主流程）

步骤：
1. 准备输入
2. 执行
3. 断言输出

```bash
# 运行命令
python -m tests.e2e.test_{feature}
```

### 3.2 异常路径

| 场景 | 模拟方法 | 期望行为 |
|------|---------|---------|
| 外部服务不可用 | mock 返回 500 | 降级处理，不崩溃 |
| 输入为空 | 传入空值 | 明确错误信息 |

---

## 四、验收命令

```bash
# 单元测试
pytest tests/unit/test_{module}.py -v

# E2E 测试
python -m tests.e2e.test_{feature}

# 全量
pytest tests/ -v
```

---

## 五、验收通过标准

- [ ] 所有 P0 验收场景通过
- [ ] 单元测试矩阵全部通过
- [ ] E2E Happy Path 通过
- [ ] 异常路径不崩溃（有 fallback）
- [ ] 无外部网络依赖（全部 mock）
```

---

## 三、测试分层定义

### Layer 1：单元测试（Unit Test）

**目标**：验证单个函数/节点的行为正确性
**规则**：
- ✅ 测试单一职责：一个 `test_xxx` 函数只测一件事
- ✅ 外部依赖全部 Mock（LLM API、文件 IO、网络请求）
- ✅ 测试覆盖：正常路径 + 空值 + 异常 + 边界
- ❌ 不发真实网络请求
- ❌ 不写数据库（用内存 mock）

```python
# ✅ 正确示例
def test_rule_match_video_source(mock_llm):
    state = {"source_type": "video", "title": "test"}
    result = rule_match_node(state)
    assert result["route_decision"]["content_type"] == "study_doc"
    mock_llm.assert_not_called()   # 规则命中时 LLM 不应该被调用

# ❌ 错误示例：发真实请求
def test_llm_classify():
    result = llm_classify_node({"title": "test"})  # 真实调 API
```

### Layer 2：集成测试（Integration Test）

**目标**：验证模块间的接口契约
**规则**：
- ✅ 可以使用真实的内部依赖（如 SubGraph 内部节点链）
- ✅ 外部服务仍然 Mock
- ✅ 验证状态流转是否符合预期

### Layer 3：端到端测试（E2E Test）

**目标**：从用户视角验证完整功能链路
**规则**：
- ✅ 覆盖完整业务流程
- ✅ 使用 Mock 替代真实 LLM / 外部 API（除非专门的集成环境）
- ✅ 断言最终输出符合用户期望
- ✅ 验证错误场景下系统不崩溃

---

## 四、Mock 规范

### 4.1 LLM Mock

```python
# Python / pytest 示例
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_llm_minimax():
    with patch("subgraphs.shared.llm.llm_minimax") as mock:
        mock.return_value = '["https://www.bilibili.com/video/BV_test/"]'
        yield mock

@pytest.fixture
def mock_llm_error():
    with patch("subgraphs.shared.llm.llm_minimax") as mock:
        mock.side_effect = RuntimeError("API 不可用")
        yield mock
```

### 4.2 文件 IO Mock

```python
from unittest.mock import patch, mock_open

def test_save_file(tmp_path):
    # 使用 pytest 的 tmp_path fixture
    result = save_to_disk("topic", [], [], tmp_path)
    assert (tmp_path / "topic" / "research_results.json").exists()
```

### 4.3 外部 HTTP Mock

```python
import responses  # pip install responses

@responses.activate
def test_feishu_notify():
    responses.add(responses.POST, "https://open.feishu.cn/...", json={"code": 0})
    result = _feishu_notify("test", "thread-1")
    assert result is True
```

---

## 五、测试文件组织规范

```
{project}/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # 全局 fixtures（mock_llm 等）
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_{module}.py # 对应 subgraphs/{module}/nodes.py 等
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_{subgraph}.py
│   └── e2e/
│       ├── __init__.py
│       └── test_{feature}.py
└── pytest.ini               # 或 pyproject.toml [tool.pytest]
```

**命名约定**：
- 文件：`test_{被测模块名}.py`
- 函数：`test_{场景描述}_{期望结果}()`
  - 示例：`test_rule_match_returns_study_doc_for_video_source()`
  - 示例：`test_llm_classify_falls_back_on_api_error()`

---

## 六、与任务流程的集成

### 任务创建时

创建任务后立刻创建 `acceptance.md` 骨架：

```bash
python3 .aies/scripts/task.py create "任务标题" --slug xxx
# 脚本自动同时创建 prd.md 和 acceptance.md 骨架
```

### implement 阶段开始前

**强制**：implement agent 开始前必须先读 `acceptance.md`，
按照测试矩阵同步实现测试代码，而不是事后补测试。

### Phase 3 完成清单新增项

```
✅ 任务完成清单
━━━━━━━━━━━━━━
...（原有项）
5. 测试验收：
   - [ ] 单元测试全部通过（pytest tests/unit/ -v）
   - [ ] E2E 测试 Happy Path 通过
   - [ ] acceptance.md 验收场景逐项打勾
```

---

## 七、质量阈值

| 类型 | 最低要求 | 目标 |
|------|---------|------|
| P0 验收场景 | 100% 通过 | 100% |
| 单元测试（核心函数） | 覆盖正常 + 异常路径 | 覆盖所有分支 |
| E2E Happy Path | 必须通过 | 必须通过 |
| 异常场景 | 不崩溃 | 有明确错误信息 |

---

## 八、禁止事项

- ❌ 没有 `acceptance.md` 就开始 implement
- ❌ 测试文件里发真实网络请求（CI 会挂）
- ❌ 测试依赖执行顺序（每个 test 必须独立可运行）
- ❌ Mock 过度（Mock 了业务逻辑本身，失去测试意义）
- ❌ 只测 Happy Path，忽略异常路径
- ❌ 测试函数名含义模糊（`test_1`, `test_func` 等）

---

## 九、ai-pipeline 项目特化规范

### 9.1 SubGraph 测试要求

每个 SubGraph **必须**有独立可运行的 `test.py`（现有模式）+
在 `tests/unit/` 下的 mock 单元测试（新增要求）：

```
subgraphs/{name}_subgraph/
├── test.py               # 真实调用（需 API Key，手动运行）
└── （tests/unit/test_{name}_subgraph.py 放项目根）

tests/
├── conftest.py           # 全局 fixtures
├── unit/
│   ├── test_research_subgraph.py
│   ├── test_transcribe_subgraph.py
│   ├── test_write_book_subgraph.py
│   ├── test_routing_subgraph.py   # 新增
│   └── test_observability.py     # 新增
└── e2e/
    └── test_video_md_pipeline.py  # 全链路 E2E
```

### 9.2 LLM Mock 标准 Fixture

```python
# tests/conftest.py
import pytest
from unittest.mock import patch

@pytest.fixture
def mock_llm_research():
    """research_subgraph 用：返回合法视频 URL 列表"""
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.return_value = '[{"title":"测试视频","url":"https://www.bilibili.com/video/BV_test/","platform":"bilibili","note":"测试"}]'
        yield m

@pytest.fixture
def mock_llm_summarize():
    """transcribe/write_book 用：返回摘要文本"""
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.return_value = "这是一段测试摘要内容，用于验证流程。"
        yield m

@pytest.fixture
def mock_llm_error():
    """模拟 LLM 不可用"""
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.side_effect = RuntimeError("MINIMAX_CN_API_KEY 未设置")
        yield m
```

### 9.3 E2E Pipeline 测试策略

E2E 测试用 **Mock LLM + 真实 LangGraph 图执行**：
- LLM 调用全部 mock（不发真实请求）
- LangGraph 图真实编译和执行（测试节点流转正确性）
- SubGraph 调用真实执行（测试状态映射正确性）

```python
# tests/e2e/test_video_md_pipeline.py
def test_pipeline_happy_path(mock_llm_research, mock_llm_summarize, tmp_path):
    """全链路 E2E：research → transcribe（mock）→ write_book → notify"""
    # 用 --urls 跳过真实 research，直接注入 mock URL
    ...
```

### 9.4 LangGraph 节点单元测试模式

```python
# 测试单个 node 函数（不启动整个 graph）
def test_rule_match_node_video_source():
    state = {
        "source_type": "video",
        "title": "AI Agent 教程",
        "summary": "介绍 LangGraph 基础用法",
    }
    result = rule_match_node(state, config=mock_config)
    assert result["match_method"] == "rule"
    assert result["route_decision"]["content_type"] == "study_doc"

# 测试 conditional edge 路由逻辑
def test_route_dispatcher_sends_all_pending():
    state = {"pending_videos": ["url1", "url2"], "_dispatched": []}
    sends = route_dispatcher(state)
    assert len(sends) == 2
```
