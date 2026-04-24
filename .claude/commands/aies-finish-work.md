# /aies:finish-work

完成当前任务，输出 Phase 3 清单并指引用户收尾。

## 执行步骤

1. 输出 Phase 3 任务完成清单（质量自检）
2. 检查 `.ai/index.md` 是否需要更新，如需要直接更新
3. 生成建议的 commit message
4. 生成完整的 `add_session` 命令供用户复制执行：

```bash
python3 .aies/scripts/session.py add \
    --title "{本次会话标题}" \
    --commit "$(git rev-parse --short HEAD)" \
    --summary "{变更摘要}"
```

5. 检查是否有新的规范约定需要沉淀到 `.aies/spec/`，有则直接修改并在 `.ai/changelog.md` 追加
