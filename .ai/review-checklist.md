# AI 代码审查清单（ai-pipeline）

> ⚠️ 每次 AI 生成代码后，**必须**逐项检查以下清单。
> 本清单在通用模板基础上，补充了 Python / LangGraph / SubGraph 特有检查项。

---

## 一、架构合规

- [ ] **主 Graph 只做编排**：没有业务算法（LLM 调用、下载、转录等应在 SubGraph）
- [ ] **SubGraph 不依赖 Pipeline**：不 import 任何 `NN-xxx/` 下的文件
- [ ] **SubGraph 结构完整**：graph/nodes/state/config/test/README 六件套齐全
- [ ] **配置通过 Config 注入**：SubGraph 内不直接读环境变量
- [ ] **入口函数签名正确**：`build_xxx_subgraph(config: XxxConfig) -> CompiledStateGraph`
- [ ] **目录命名规范**：SubGraph 用 `{name}_subgraph/`，Pipeline 用 `{NN}-{slug}/`

---

## 二、LangGraph 特定

- [ ] **State 用 TypedDict**：不用 dataclass / BaseModel
- [ ] **并行字段有 reducer**：`Annotated[List, lambda a, b: a + b]`
- [ ] **`List[Send]` 来源正确**：只从 conditional edge 返回，不从 node 返回
- [ ] **node 返回部分 State**：`Dict[str, Any]`，不返回整个 State
- [ ] **父子 State 手动映射**：SubGraph 调用用显式字段映射，不直接传父 State
- [ ] **Checkpointer 单例**：进程级只建一次，`SqliteSaver` + `check_same_thread=False`
- [ ] **NodeInterrupt 有 id**：`raise NodeInterrupt(msg, id="unique-id")`

---

## 三、数据完整性

- [ ] **thread_id 贯穿始终**：从 run.py → 主 State → 审核 DB → 日志都能追踪
- [ ] **HITL 审核状态独立存储**：不塞进 Checkpointer 的 State
- [ ] **HITL 有超时机制**：避免 pending 永久挂起
- [ ] **并行任务输出隔离**：每任务独立 `task-{idx}/` 子目录
- [ ] **失败场景 State 正确**：`failed_videos` 有被填入、`step="error"` 有被设置

---

## 四、边界条件

- [ ] **0 任务场景**：所有视频被 reject 时不崩
- [ ] **单任务场景**：只有 1 个视频时 fan-out 正确
- [ ] **超大输入**：列表过长时有截断或分批
- [ ] **空 State 字段**：`state.get("xxx", default)` 而非 `state["xxx"]`（`total=False`）
- [ ] **SubGraph 失败**：主 Graph 捕获异常并写入 `failed_videos`，不让 Pipeline 整体崩溃
- [ ] **视频 URL 格式**：不是每个 URL 都能下载，有失败时正确降级

---

## 五、错误处理

- [ ] **SubGraph 异常被 catch**：`node_transcribe_single` 要用 try/except 包住 `subgraph.invoke`
- [ ] **错误信息清晰**：`state["error"]` 包含失败原因而不是泛泛 "failed"
- [ ] **日志带 node 前缀**：`[main:xxx]` / `[{subgraph}:{node}]`
- [ ] **外部调用有超时**：LLM / HTTP / 飞书通知都要有 timeout

---

## 六、性能

- [ ] **SubGraph 单例缓存**：`_get_xxx_subgraph()` 用 global 缓存，不每次都 build
- [ ] **并行度控制**：fan-out 时如果视频很多（>20），考虑限制并发数
- [ ] **LLM 调用不重复**：同一数据不反复调 LLM
- [ ] **SQLite 连接复用**：`check_same_thread=False` + 单例

---

## 七、日志与可观测性

- [ ] **关键节点有日志**：每个 node 入口至少有一行 `print(f"[xx:yy] ...")`
- [ ] **日志含 thread_id**：HITL / 异步场景必须能反查
- [ ] **不泄漏敏感信息**：FEISHU_APP_SECRET / API Key 不能出现在日志
- [ ] **错误日志含上下文**：`video_url` / `task_idx` / `topic` 等

---

## 八、Python 风格

- [ ] **模块有 docstring**：顶部说明职责
- [ ] **State / Config 字段有注释**：每个字段一行说明
- [ ] **类型注解完整**：公开 API（build_xxx / node 函数）必须有
- [ ] **路径用 pathlib**：不用 `"/Users/..."` 拼字符串
- [ ] **不硬编码 venv 路径**：当前 `main_graph.py` 有硬编码 Python 3.9 路径，是技术债
- [ ] **异常链传递**：`raise XXX from e` 保留原因

---

## 九、AI 常见盲区（重点）

- [ ] **硬编码本机路径**：AI 很容易写 `/Users/zyongzhu/...`
- [ ] **遗漏 Reducer**：AI 经常忘记给并行字段加 `Annotated`
- [ ] **把 Send 放进 node**：AI 容易从 node 返回 Send（运行时才会报错）
- [ ] **SubGraph 里读环境变量**：应走 Config
- [ ] **`state["xx"]` 未检查 None**：`total=False` 的 TypedDict 所有字段都可能缺失
- [ ] **遗漏 test.py**：新 SubGraph 没有独立测试
- [ ] **遗漏更新 `.ai/index.md`**：新增 SubGraph / Pipeline / node 后要更新地图

---

## 十、文档更新

- [ ] **更新 `.ai/index.md`**：新增 SubGraph / Pipeline / node / State 字段
- [ ] **更新 `.ai/changelog.md`**：本次变更简短记录
- [ ] **更新 SubGraph 的 README.md**：State / Config / 调用方式
- [ ] **更新 Pipeline 的 readme.md**：CLI 命令 / 流程图（如变化）
- [ ] **新约定沉淀到 `.aies/spec/`**：如果发现新模式
- [ ] **已知技术债补到 `.ai/known-issues.md`**：如果本次修复暴露了其他问题

---

## 使用方式

1. AI 生成代码后，对照此清单逐项检查
2. 发现问题标注 `❌`，并要求 AI 修正
3. 全部通过标注 `✅`，可以提交
4. 如果发现新盲区，**补充到此清单中**（并在 `.ai/changelog.md` 记录）
