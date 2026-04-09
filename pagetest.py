import os
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www.theinformation.com/subscriber_feed"
STATE_FILE = Path("state.json")
DEBUG_HTML = Path("debug_response.html")
USERNAME = os.environ.get("THEINFO_USERNAME")
PASSWORD = os.environ.get("THEINFO_PASSWORD")

print("脚本启动")

if not USERNAME or not PASSWORD:
    raise RuntimeError("缺少 THEINFO_USERNAME 或 THEINFO_PASSWORD 环境变量")

with sync_playwright() as p:
    print("Playwright 已启动")
    browser = p.chromium.launch(headless=True)
    print("浏览器已启动")

    context = browser.new_context(
        storage_state=str(STATE_FILE),
        http_credentials={
            "username": USERNAME,
            "password": PASSWORD,
        }
    )
    print("context 已创建")

    page = context.new_page()
    print("page 已创建，准备打开 URL")

    response = page.goto(URL, timeout=60000, wait_until="domcontentloaded")
    print("goto 已返回")

    page.wait_for_timeout(5000)
    print("等待 5 秒结束")

    content = page.content()
    print("已拿到 content，长度：", len(content))
    print("最终 URL:", page.url)
    print("标题:", page.title())
    print("HTTP 状态码:", response.status if response else "No response")

    DEBUG_HTML.write_text(content, encoding="utf-8")
    print("已写入 debug_response.html")

    browser.close()
    print("浏览器已关闭，脚本结束")
