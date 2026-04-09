# RSS Automation Guide

## 代码作用

这个项目用于自动抓取 The Information 的订阅 RSS，并整理为结构化 CSV 文件。

当前实现包含两层能力：

1. `fetch_in0407.py`
   负责实际抓取和清洗 RSS 内容。
   输出字段为：
   - `标题`
   - `时间`
   - `作者`
   - `链接`
   - `内容`

2. `automate_rss.py`
   负责定时任务对应的业务流程：
   - 每天生成前一天 PDT 的日 CSV
   - 每周五生成最近 7 天的周合并 CSV
   - 每次生成后自动执行 `git add / commit / push`


## 依赖文件

- `state.json`
  必需。用于保存 Playwright 登录态。

- 环境变量 `THEINFO_USERNAME` / `THEINFO_PASSWORD`
  必需。用于提供订阅 RSS 的 HTTP Basic Auth 账号密码。

- `pagetest.py`
  保留的验证脚本，用来确认当前 `state.json` 和 basic auth 是否还能拿到 RSS 页面。

- `.venv/`
  Python 虚拟环境。定时任务通过其中的 Python 执行。


## 主要文件说明

- `fetch_in0407.py`
  抓取 RSS，清洗正文，并支持按 `America/Los_Angeles` 日期过滤条目。

- `automate_rss.py`
  自动化主流程脚本。

- `run_rss_job.sh`
  cron 调用入口。

- `rss_crawl.crontab`
  当前使用的 cron 配置模板。

- `daily_csv/`
  存放每日生成的 CSV 文件，文件名格式：
  `YYYY-MM-DD.csv`

- `weekly_csv/`
  存放每周合并后的 CSV 文件，文件名格式：
  `YYYY-MM-DD_to_YYYY-MM-DD.csv`

- `logs/`
  存放 cron 运行日志。


## 自动运行规则

当前建议安装到系统 `crontab` 的规则如下：

```cron
0 4 * * * /home/ubuntu/work/rss-crawl/run_rss_job.sh daily >> /home/ubuntu/work/rss-crawl/logs/daily.log 2>&1
0 5 * * 5 /home/ubuntu/work/rss-crawl/run_rss_job.sh weekly >> /home/ubuntu/work/rss-crawl/logs/weekly.log 2>&1
```

含义：

- 服务器使用 `UTC` 时区时，每天 `04:00 UTC`
  执行一次日抓取
- 对应北京时间 `12:00`

- 服务器使用 `UTC` 时区时，每周五 `05:00 UTC`
  执行一次周合并
- 对应北京时间 `13:00`

之所以直接写成 `UTC` 时间，是因为当前机器实际按 `UTC` 解释 cron 表达式。相比依赖 `CRON_TZ=Asia/Shanghai`，直接写成 `UTC` 时间更稳妥，也更容易排查。


## 日抓取逻辑

日抓取使用北京时间当天减 1 天，得到目标日期。

例如：

- 北京时间 `2026-04-07 12:00` 运行
- 目标日期为 `2026-04-06`
- 过滤规则按照 RSS 上时间转换到 `America/Los_Angeles` 后的日期判断
- 结果输出到：
  `daily_csv/2026-04-06.csv`

CSV 列为：

- `标题`
- `时间`
- `作者`
- `链接`
- `内容`

正文会在遇到以下栏目时截断：

- `Upcoming Events`
- `Recommended Newsletter`
- `New From Our Reporters`
- `Today on The Information’s TITV`
- `Today on The Information's TITV`
- `What We’re Reading`
- `What We're Reading`


## 周合并逻辑

每周五北京时间 `13:00` 运行周任务时：

- 结束日期 = 当天减 1 天
- 起始日期 = 结束日期减 6 天
- 合并对应的 7 个日 CSV
- 输出到 `weekly_csv/起始日期_to_结束日期.csv`

例如：

- 北京时间 `2026-04-11 13:00` 执行周任务
- 合并范围为 `2026-04-04` 到 `2026-04-10`
- 输出文件：
  `weekly_csv/2026-04-04_to_2026-04-10.csv`


## Git 自动上传逻辑

每次日文件或周文件生成后，`automate_rss.py` 会自动执行：

```bash
git add
git commit
git push origin main
```

提交信息格式：

- 日文件：
  `Add daily RSS CSV for YYYY-MM-DD`

- 周文件：
  `Add weekly RSS CSV for YYYY-MM-DD to YYYY-MM-DD`


## 手动使用流程

### 1. 手动抓取一次 RSS

```bash
export THEINFO_USERNAME="your_email@example.com"
export THEINFO_PASSWORD="your_password"
python3 fetch_in0407.py
```

默认会输出到：

```bash
theinformation_feed.csv
```


### 2. 手动抓取指定 PDT 日期

```bash
python3 fetch_in0407.py --target-date 2026-04-06 --csv-output daily_csv/2026-04-06.csv
```


### 3. 手动执行日任务

```bash
export THEINFO_USERNAME="your_email@example.com"
export THEINFO_PASSWORD="your_password"
./.venv/bin/python automate_rss.py --mode daily
```


### 4. 手动执行周任务

```bash
export THEINFO_USERNAME="your_email@example.com"
export THEINFO_PASSWORD="your_password"
./.venv/bin/python automate_rss.py --mode weekly
```


### 5. 只测试生成文件，不执行 git

```bash
./.venv/bin/python automate_rss.py --mode daily --skip-git
./.venv/bin/python automate_rss.py --mode weekly --skip-git
```


### 6. 用指定时间做演练

```bash
./.venv/bin/python automate_rss.py --mode daily --now 2026-04-07T12:00:00 --skip-git
./.venv/bin/python automate_rss.py --mode weekly --now 2026-04-10T13:00:00 --skip-git
```


## 使用前提

以下条件必须满足：

1. `state.json` 仍然有效
2. 已配置环境变量 `THEINFO_USERNAME` 和 `THEINFO_PASSWORD`
3. 当前机器在定时触发时开机
4. `cron` 服务正常
5. 当前机器能正常执行 `git push origin main`
6. `.venv` 中的依赖完整可用


## 常驻环境变量

如果希望环境变量长期生效，可以写入当前用户的 shell 配置文件，例如 `~/.bashrc`：

```bash
export THEINFO_USERNAME="your_email@example.com"
export THEINFO_PASSWORD="your_password"
```

写入后执行：

```bash
source ~/.bashrc
```

如果任务由 `cron` 执行，建议在 `crontab` 中显式注入环境变量，或在 `run_rss_job.sh` 中先 `source ~/.bashrc` 后再运行脚本，否则 `cron` 默认不会继承交互式 shell 的环境变量。


## 常见问题排查

### 1. 抓不到 RSS

优先检查：

- `state.json` 是否过期
- `pagetest.py` 是否还能成功访问订阅页
- `debug_response.html` 中返回的是不是登录页或错误页


### 2. 自动任务没有执行

检查：

```bash
crontab -l
```

以及日志：

```bash
logs/daily.log
logs/weekly.log
```


### 3. 生成了 CSV 但没有推送到 GitHub

检查：

- 当前机器是否还能 `git push origin main`
- SSH key 在 cron 环境里是否可用
- git 用户配置是否存在

可手动验证：

```bash
git config user.name
git config user.email
ssh -T git@github.com
```


## 当前设计说明

- 日文件和周文件分别放在独立子文件夹中
- 如果目标日期没有文章，也会生成只有表头的 CSV
- `state.json` 不参与自动提交，避免把登录态变更推到远端
- `pagetest.py` 保留，用作人工排障验证
