import argparse
import csv
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_in0407 import BASE_DIR, CSV_FIELDS, run_fetch


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
DAILY_DIR = BASE_DIR / "daily_csv"
WEEKLY_DIR = BASE_DIR / "weekly_csv"
DAILY_BRANCH = "main"
WEEKLY_BRANCH = "main"
AUTO_COMMIT_RULES_FILE = BASE_DIR / "AUTO_COMMIT_RULES.md"
AUTO_UPLOAD_LOG_FILE = BASE_DIR / "AUTO_UPLOAD_LOG.md"


def parse_args():
    parser = argparse.ArgumentParser(
        description="自动执行 The Information 的日抓取、周合并和 git 上传。"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", "all"],
        default="all",
        help="执行模式: daily 只生成日文件, weekly 只生成周文件, all 两者都可按条件执行",
    )
    parser.add_argument(
        "--now",
        help="覆盖当前北京时间，格式 YYYY-MM-DDTHH:MM:SS，用于测试",
    )
    parser.add_argument(
        "--skip-push",
        action="store_true",
        help="只生成文件和本地 commit，不执行 git push",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="只生成文件，不执行任何 git add/commit/push",
    )
    return parser.parse_args()


def get_now_beijing(now_override: str | None) -> datetime:
    if now_override:
        parsed = datetime.fromisoformat(now_override)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=BEIJING_TZ)
        return parsed.astimezone(BEIJING_TZ)
    return datetime.now(BEIJING_TZ)


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
    )
    if result.stdout.strip():
        print(f"$ {' '.join(args)}")
        print(result.stdout.strip())
    if result.stderr.strip():
        print(f"$ {' '.join(args)} [stderr]")
        print(result.stderr.strip())
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def repo_relative(path: Path) -> str:
    return str(path.relative_to(BASE_DIR))


def is_auto_commit_allowed(path: Path) -> bool:
    rel_path = repo_relative(path)
    if rel_path == "state.json":
        return False
    if path.suffix == ".py":
        return False
    if path.suffix == ".md":
        return True
    if rel_path.startswith("daily_csv/") and path.suffix == ".csv":
        return True
    if rel_path.startswith("weekly_csv/") and path.suffix == ".csv":
        return True
    return False


def get_changed_repo_paths() -> list[Path]:
    result = run_command(["git", "status", "--porcelain"], check=True)
    changed_paths = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        changed_paths.append(BASE_DIR / raw_path)
    return changed_paths


def collect_auto_commit_paths(preferred_paths: list[Path]) -> list[Path]:
    changed_resolved = {path.resolve() for path in get_changed_repo_paths() if path.exists()}
    selected_paths = []
    seen = set()

    for path in preferred_paths:
        if not path.exists():
            continue
        if not is_auto_commit_allowed(path):
            continue
        resolved = path.resolve()
        if resolved not in changed_resolved:
            continue
        if resolved in seen:
            continue
        selected_paths.append(path)
        seen.add(resolved)

    return selected_paths


def append_upload_log(entry_lines: list[str]) -> Path:
    existing = AUTO_UPLOAD_LOG_FILE.read_text(encoding="utf-8") if AUTO_UPLOAD_LOG_FILE.exists() else ""
    header = "# Auto Upload Log\n\n"
    if not existing:
        existing = header
    elif not existing.startswith("# Auto Upload Log"):
        existing = header + existing

    entry = "\n".join(entry_lines).strip() + "\n\n"
    AUTO_UPLOAD_LOG_FILE.write_text(existing + entry, encoding="utf-8")
    return AUTO_UPLOAD_LOG_FILE


def git_commit_and_push(paths: list[Path], message: str, skip_push: bool) -> None:
    commit_paths = collect_auto_commit_paths(paths)
    if not commit_paths:
        print(f"git no allowed changes for: {[repo_relative(path) for path in paths]}")
        return

    print(f"git staging: {[repo_relative(path) for path in commit_paths]}")
    run_command(["git", "add", "--", *[repo_relative(path) for path in commit_paths]])
    run_command(["git", "commit", "-m", message])
    if not skip_push:
        run_command(["git", "push", "origin", "main"])


def daily_output_path(target_date_str: str) -> Path:
    return DAILY_DIR / f"{target_date_str}.csv"


def weekly_output_path(start_date_str: str, end_date_str: str) -> Path:
    return WEEKLY_DIR / f"{start_date_str}_to_{end_date_str}.csv"


def generate_daily_csv(now_beijing: datetime) -> tuple[Path, str]:
    target_date = now_beijing.date() - timedelta(days=1)
    target_date_str = target_date.isoformat()
    output_path = daily_output_path(target_date_str)
    print(f"daily start target_date={target_date_str} output={output_path}")
    rows, csv_path = run_fetch(csv_output=output_path, target_date=target_date)
    print(f"daily rows={len(rows)} target_date={target_date_str} output={csv_path}")
    return csv_path, target_date_str


def merge_csv_files(source_paths: list[Path], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_rows = []
    missing_sources = []

    for source_path in source_paths:
        if not source_path.exists():
            missing_sources.append(source_path)
            continue
        with source_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            for row in reader:
                merged_rows.append({field: row.get(field, "") for field in CSV_FIELDS})

    if missing_sources:
        print(
            "weekly missing daily csv files: "
            + ", ".join(str(path.relative_to(BASE_DIR)) for path in missing_sources)
        )

    with output_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(merged_rows)

    return len(merged_rows)


def generate_weekly_csv(now_beijing: datetime) -> tuple[Path, list[Path], str, str, int]:
    end_date = now_beijing.date() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)
    source_paths = [
        daily_output_path((start_date + timedelta(days=offset)).isoformat())
        for offset in range(7)
    ]
    output_path = weekly_output_path(start_date.isoformat(), end_date.isoformat())
    print(
        "weekly start "
        f"start_date={start_date.isoformat()} end_date={end_date.isoformat()} output={output_path}"
    )
    row_count = merge_csv_files(source_paths, output_path)
    print(
        "weekly "
        f"rows={row_count} start_date={start_date.isoformat()} "
        f"end_date={end_date.isoformat()} output={output_path}"
    )
    return output_path, source_paths, start_date.isoformat(), end_date.isoformat(), row_count


def should_run_weekly(now_beijing: datetime) -> bool:
    return now_beijing.weekday() == 4 and now_beijing.hour >= 13


def main():
    args = parse_args()
    try:
        now_beijing = get_now_beijing(args.now)
        print(
            "job start "
            f"mode={args.mode} now_beijing={now_beijing.isoformat()} "
            f"skip_git={args.skip_git} skip_push={args.skip_push}"
        )

        if args.mode in {"daily", "all"}:
            daily_path, target_date_str = generate_daily_csv(now_beijing)
            daily_log_path = append_upload_log(
                [
                    f"## Daily {now_beijing.isoformat()}",
                    f"- target_date: {target_date_str}",
                    f"- csv: {repo_relative(daily_path)}",
                ]
            )
            if not args.skip_git:
                git_commit_and_push(
                    paths=[daily_path, daily_log_path],
                    message=f"Add daily RSS CSV for {target_date_str}",
                    skip_push=args.skip_push,
                )

        if args.mode == "weekly" or (args.mode == "all" and should_run_weekly(now_beijing)):
            weekly_path, _, start_date_str, end_date_str, _ = generate_weekly_csv(now_beijing)
            weekly_log_path = append_upload_log(
                [
                    f"## Weekly {now_beijing.isoformat()}",
                    f"- start_date: {start_date_str}",
                    f"- end_date: {end_date_str}",
                    f"- csv: {repo_relative(weekly_path)}",
                ]
            )
            if not args.skip_git:
                git_commit_and_push(
                    paths=[weekly_path, weekly_log_path],
                    message=f"Add weekly RSS CSV for {start_date_str} to {end_date_str}",
                    skip_push=args.skip_push,
                )

        print("job finished")
    except Exception as exc:
        print(f"job failed: {exc.__class__.__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
