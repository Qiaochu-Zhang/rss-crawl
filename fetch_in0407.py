import argparse
import csv
import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


URL = "https://www.theinformation.com/subscriber_feed"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
DEBUG_FILE = BASE_DIR / "debug_response.html"
DEFAULT_CSV_FILE = BASE_DIR / "theinformation_feed.csv"
DEFAULT_USERNAME = os.environ.get("THEINFO_USERNAME")
DEFAULT_PASSWORD = os.environ.get("THEINFO_PASSWORD")

FEED_TIMEZONE = ZoneInfo("America/Los_Angeles")
CONTENT_CUTOFF_MARKERS = [
    "Upcoming Events",
    "Recommended Newsletter",
    "New From Our Reporters",
    "Today on The Information’s TITV",
    "Today on The Information's TITV",
    "What We’re Reading",
    "What We're Reading",
]
CSV_FIELDS = ["标题", "时间", "作者", "链接", "内容"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="抓取 The Information subscriber feed，并整理为结构化 CSV。"
    )
    parser.add_argument("--url", default=URL, help="RSS/Atom feed 地址")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_FILE,
        help="Playwright storage state 文件路径，默认使用 state.json",
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help="HTTP Basic Auth 用户名，默认读取环境变量 THEINFO_USERNAME",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="HTTP Basic Auth 密码，默认读取环境变量 THEINFO_PASSWORD",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=DEFAULT_CSV_FILE,
        help="整理后的 CSV 输出路径，列为标题/时间/作者/链接/内容",
    )
    parser.add_argument(
        "--target-date",
        help="只保留该日期的文章，格式 YYYY-MM-DD，按 America/Los_Angeles 日期过滤",
    )
    parser.add_argument(
        "--debug-output",
        type=Path,
        default=DEBUG_FILE,
        help="原始响应调试输出路径",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=60000,
        help="页面请求超时时间，毫秒",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=3000,
        help="打开页面后的额外等待时间，毫秒",
    )
    return parser.parse_args()


def html_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment or "", "html.parser")
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{2,}", "\n\n", text).strip()


def truncate_content(text: str) -> str:
    if not text:
        return ""

    cutoff_index = len(text)
    for marker in CONTENT_CUTOFF_MARKERS:
        marker_index = text.find(marker)
        if marker_index != -1:
            cutoff_index = min(cutoff_index, marker_index)

    truncated = text[:cutoff_index]
    return re.sub(r"\n{2,}", "\n\n", truncated).strip()


def extract_feed_xml_from_text(text: str) -> str:
    if not text:
        return ""

    match = re.search(
        r"((?:<\?xml\b.*?\?>\s*)?<feed\b.*?</feed>)",
        text,
        flags=re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    stripped = text.strip()
    if stripped.startswith("<?xml") or stripped.startswith("<feed"):
        return stripped

    return ""


def extract_feed_xml_from_page(page) -> str:
    pre = page.locator("pre")
    if pre.count():
        pre_text = pre.first.inner_text(timeout=5000)
        xml_text = extract_feed_xml_from_text(html.unescape(pre_text))
        if xml_text:
            return xml_text

    content = page.content()
    unescaped = html.unescape(content)
    return extract_feed_xml_from_text(unescaped)


def fetch_feed_xml(
    url: str,
    state_file: Path,
    username: str | None,
    password: str | None,
    timeout_ms: int,
    wait_ms: int,
    debug_output: Path,
) -> str:
    if not state_file.exists():
        raise FileNotFoundError(f"缺少 state 文件: {state_file}")

    context_kwargs = {"storage_state": str(state_file)}
    if username and password:
        context_kwargs["http_credentials"] = {
            "username": username,
            "password": password,
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            response = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)

            raw_text = response.text() if response else ""
            xml_text = extract_feed_xml_from_text(raw_text)
            if not xml_text:
                xml_text = extract_feed_xml_from_page(page)

            if not xml_text:
                debug_output.write_text(page.content(), encoding="utf-8")
                raise RuntimeError(
                    f"未拿到有效 Atom feed，已将页面内容写入 {debug_output}"
                )

            debug_output.write_text(xml_text, encoding="utf-8")
            return xml_text
        finally:
            browser.close()


def parse_feed_timestamp(value: str) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(FEED_TIMEZONE)


def parse_atom(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []

    for entry in root.findall("atom:entry", ATOM_NS):
        title = entry.findtext("atom:title", default="", namespaces=ATOM_NS)
        published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
        updated = entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
        author = entry.findtext("atom:author/atom:name", default="", namespaces=ATOM_NS)
        content_html_raw = entry.findtext("atom:content", default="", namespaces=ATOM_NS)
        content_html = html.unescape(content_html_raw or "")
        time_value = published or updated
        feed_datetime = parse_feed_timestamp(time_value)
        link = ""

        for link_elem in entry.findall("atom:link", ATOM_NS):
            if link_elem.attrib.get("rel") == "alternate":
                link = link_elem.attrib.get("href", "")
                break

        rows.append(
            {
                "标题": title,
                "时间": time_value,
                "作者": author,
                "链接": link,
                "内容": truncate_content(html_to_text(content_html)),
                "feed_local_date": feed_datetime.date().isoformat() if feed_datetime else "",
            }
        )

    return rows


def filter_rows_by_target_date(rows: list[dict], target_date: date | None) -> list[dict]:
    if target_date is None:
        return rows

    target_value = target_date.isoformat()
    return [row for row in rows if row.get("feed_local_date") == target_value]


def save_csv(rows: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def run_fetch(
    csv_output: Path,
    target_date: date | None = None,
    url: str = URL,
    state_file: Path = STATE_FILE,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
    debug_output: Path = DEBUG_FILE,
    timeout_ms: int = 60000,
    wait_ms: int = 3000,
) -> tuple[list[dict], Path]:
    xml_text = fetch_feed_xml(
        url=url,
        state_file=state_file,
        username=username,
        password=password,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        debug_output=debug_output,
    )
    rows = parse_atom(xml_text)
    rows = filter_rows_by_target_date(rows, target_date)
    save_csv(rows, csv_output)
    return rows, csv_output


def main():
    args = parse_args()
    target_date = (
        date.fromisoformat(args.target_date) if args.target_date else None
    )

    rows, csv_path = run_fetch(
        csv_output=args.csv_output,
        target_date=target_date,
        url=args.url,
        state_file=args.state_file,
        username=args.username,
        password=args.password,
        debug_output=args.debug_output,
        timeout_ms=args.timeout_ms,
        wait_ms=args.wait_ms,
    )

    print(f"抓取完成，共 {len(rows)} 条")
    if target_date:
        print(f"筛选日期(America/Los_Angeles): {target_date.isoformat()}")
    print(f"CSV: {csv_path}")
    print(f"调试文件: {args.debug_output}")


if __name__ == "__main__":
    main()
