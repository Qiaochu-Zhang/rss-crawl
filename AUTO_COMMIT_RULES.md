# Auto Commit Rules

自动提交白名单如下：

- 所有 `.md` 文件可以自动提交
- `daily_csv/` 目录下的 `.csv` 文件可以自动提交
- `weekly_csv/` 目录下的 `.csv` 文件可以自动提交

自动提交黑名单如下：

- 所有 `.py` 文件不自动提交
- `state.json` 永远不自动提交

执行规则：

- `automate_rss.py` 在执行 `git add / commit / push` 前，会先扫描当前仓库改动
- 只有命中白名单且不在黑名单内的文件会被自动暂存和提交
- 这个规则文件本身是 `.md` 文件，因此允许被自动提交
