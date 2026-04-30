# zyongzhu — Journal 1

## 2026-04-24 15:22:08 — 落地 AIES 脚手架

**摘要**: 安装 .ai/ + .aies/ 目录，定制化填充 architecture/code-style/glossary/known-issues，总计 52 个文件


## 2026-04-24 15:42:40 — 落地 AIES 脚手架到 ai-pipeline（完整版）

**Commit**: `119efa6`

**摘要**: 基于 /Users/zyongzhu/workbase/agent/ai-engineering-scaffold 的 bootstrap.py --mode merge 落地。未覆盖任何原有文件（HERMES_TASK / subgraphs / 01-video-md 全保留）。核心产出：(1) 定制化填充 .aies/spec/architecture.md 写死 SubGraph 设计约束（6 文件结构 / build_xxx_subgraph(config) 签名 / State 独立模式 / fan-out 只能从 conditional edge 返回 / Reducer 强制等）；(2) .aies/spec/code-style.md 第十节沉淀项目血泪史 5 反模式；(3) .ai/index.md 按真实 SubGraph+Pipeline 结构重写，含 State schema/持久化/环境变量；(4) .ai/known-issues.md 从 HERMES_TASK roadmap 提炼 17 项技术债并分 🔴🟠🟡 三级，附 AI 提醒规则；(5) CLAUDE.md 承接 Hermes 调度背景。已验收：session.py / task.py 跑通，开发者 zyongzhu 已初始化，示范任务 04-24-langfuse-integration 已创建。后续 TODO（写进 known-issues）：把 vault/ 下的 subgraph-design-spec.md 迁入 .aies/spec/、重写 main_graph.py 硬编码路径、接入 Langfuse。


## 2026-04-27 09:57:13 — 批量拉取 workspace 41 仓库（方案 A：只拉干净仓库）

**摘要**: 全景扫描 /Users/zyongzhu/workbase/agent/ 与 /Users/zyongzhu/workbase/github/moon/ 下 41 个 git 仓库状态。按方案 A 执行：只拉 clean+behind>0 的仓库，DIRTY 仓库全部跳过保留原状。成功拉取 7 个：agent-knowledge-service(+3) / monitor-rule-mgr(+56) / o2-saas-login(+9) / yky-dx-admin-backend(+5) / yky-dx-scripts(+10) / pipeline(+1) / o2-saas-gdt-api（修复 ref 冲突后）。顺手解决两个坑：(1) macOS 无 timeout 命令，改用 perl alarm 实现超时；(2) o2-saas-gdt-api 的 Git ref 命名空间冲突（origin/fix 同时存在 file-ref 和 dir-ref），用 remote prune + update-ref -d 清掉旧的 packed-ref 解决。ai-pipeline 本身本地领先 1，未处理，等用户决定 push 时机。脚本保存在 /tmp/aies-git-check.sh 和 /tmp/aies-git-pull.sh 可复用。


## 2026-04-27 15:36:01 — 开发机 9.134.56.26 数据盘 /data 在线扩容 50G→250G

**摘要**: DevCloud 平台已扩 /dev/vdb 50G→250G，机器内 ext4 文件系统未跟进（49G 100% 满）。诊断：TencentOS 3.2，/dev/vdb 是裸盘无分区表（Partition Table: loop）+ ext4，属扩容文档『数据盘场景二』，直接 resize2fs /dev/vdb 在线完成，无需 umount/reboot/分区操作。执行结果：49G→246G，已用 47G 不变（数据零丢失），可用 0→189G，使用率 100%→20%，整个扩容 1 秒完成。主要踩坑不在扩容本身而在 SSH：~/.ssh/config 默认 User=root，公钥要加到 /root/.ssh/authorized_keys 而非 /home/zyongzhu/.ssh/authorized_keys。指纹核对 SHA256:Fr1rZrIkak... 才确认到位。后续：把『ext4 裸盘 resize2fs』和『SSH 公钥要看 ssh -G 实际用户』沉淀到 ai-engineering-scaffold 的 known-issues 通用模板。系统盘 /dev/vda1 当前 76%，建议近期处理。

