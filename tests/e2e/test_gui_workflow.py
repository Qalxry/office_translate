"""Browser workflow smoke test without a real model or network provider."""

from __future__ import annotations

import socket
import threading
import time
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
import uvicorn
from openpyxl.cell.rich_text import CellRichText, InlineFont, TextBlock

from office_translate.gui.server import create_app


pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "Hello"
    sheet["B1"] = "World"
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def _rich_workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "翻译"
    sheet["A1"] = CellRichText(
        [
            "Hello ",
            TextBlock(InlineFont(b=True, color="FFFF0000"), "world"),
        ]
    )
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def _chromium_path() -> Path:
    browser_path = next(
        (
            path
            for path in Path.home().glob(
                ".cache/ms-playwright/chromium-*/chrome-linux64/chrome"
            )
            if path.is_file()
        ),
        None,
    )
    if browser_path is None:
        pytest.fail(
            "未找到 Chromium；请先运行 `playwright install chromium` 再执行 e2e。"
        )
    return browser_path


def _create_browser_job(
    page,
    gui_server: str,
    name: str,
    *,
    workbook: bytes | None = None,
) -> None:
    upload = page.request.post(
        f"{gui_server}/api/upload",
        multipart={
            "file": {
                "name": f"{name}.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "buffer": workbook if workbook is not None else _workbook_bytes(),
            }
        },
    )
    assert upload.ok
    created = page.request.post(
        f"{gui_server}/api/jobs",
        data={"job": name, "input": upload.json()["path"]},
    )
    assert created.ok


def _tab_to(page, locator, *, max_steps: int = 120) -> None:
    """Reach a visible control using only sequential keyboard navigation."""
    for _ in range(max_steps):
        if locator.evaluate("element => element === document.activeElement"):
            return
        page.keyboard.press("Tab")
    raise AssertionError("Tab navigation did not reach the requested control")


@pytest.fixture
def gui_server(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"work_dir: {tmp_path / 'work'}\noutput_dir: output\nsep: '\\n'\n",
        encoding="utf-8",
    )
    app = create_app(
        config_path=str(config),
        glossary_path=str(tmp_path / "glossary.json"),
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=3)
        raise RuntimeError("GUI test server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_gui_manual_translation_review_export_and_recovery(gui_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(_chromium_path()),
        )
        page = browser.new_page(viewport={"width": 900, "height": 700})
        page.goto(gui_server, wait_until="networkidle")
        assert page.title() == "office_translate"
        assert page.get_by_text("选择或新建任务").is_visible()

        _create_browser_job(page, gui_server, "browser_workflow")

        page.reload(wait_until="networkidle")
        page.locator("button.job-select").filter(has_text="browser_workflow").click()
        page.get_by_role("button", name="开始提取").click()
        page.get_by_text("提取完成，2 条文本").wait_for()

        page.get_by_role("button", name="手动翻译").click()
        page.locator("#manual-translations").fill("你好\n")
        page.get_by_role("button", name="保存并进入下一步").click()
        page.get_by_role("button", name="确认并保存").click()
        page.get_by_role("heading", name="导出").wait_for()

        # The blank second translation was explicitly confirmed; export is now
        # enabled and should produce both files without any model call.
        export_button = page.get_by_role("button", name="生成输出文件")
        assert export_button.is_enabled()
        export_button.click()
        page.wait_for_timeout(800)
        export_errors = [
            text
            for text in page.locator('[role="alert"]').all_text_contents()
            if text.strip()
        ]
        assert not export_errors, export_errors
        page.get_by_text("仅译文版", exact=True).wait_for()
        page.get_by_text("原文-译文对照版", exact=True).wait_for()

        # Refresh recovery returns to a persisted exported job, rather than an
        # empty-state illusion.  Check a second supported desktop viewport too.
        page.reload(wait_until="networkidle")
        page.set_viewport_size({"width": 1024, "height": 768})
        page.locator("button.job-select").filter(has_text="browser_workflow").click()
        page.get_by_text("导出").first.wait_for()
        assert page.get_by_text("仅译文版", exact=True).is_visible()

        # The supported large desktop viewport preserves the same recovered
        # workflow without introducing page-level horizontal overflow.
        page.set_viewport_size({"width": 1280, "height": 800})
        assert page.get_by_text("仅译文版", exact=True).is_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )

        # Keyboard reachability: Tab must land on a native focusable control.
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement && document.activeElement.tagName") in {
            "BUTTON",
            "A",
            "INPUT",
            "SELECT",
            "TEXTAREA",
        }

        # The GUI gives an actionable .xls explanation before it reaches task
        # creation; this path never contacts a provider.
        page.goto(gui_server, wait_until="networkidle")
        page.locator("input[type=file]").set_input_files(
            {
                "name": "legacy.xls",
                "mimeType": "application/vnd.ms-excel",
                "buffer": b"legacy",
            }
        )
        page.get_by_text("另存为").first.wait_for()
        browser.close()


def test_gui_keyboard_only_core_path_and_modal_focus(gui_server):
    """Complete the local core path without pointer input and verify dialog focus."""
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(_chromium_path()),
        )
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.goto(gui_server, wait_until="networkidle")
        _create_browser_job(page, gui_server, "keyboard_workflow")
        page.reload(wait_until="networkidle")

        job_button = page.locator("button.job-select").filter(
            has_text="keyboard_workflow"
        )
        _tab_to(page, job_button)
        page.keyboard.press("Enter")

        extract_button = page.get_by_role("button", name="开始提取")
        _tab_to(page, extract_button)
        page.keyboard.press("Enter")
        page.get_by_text("提取完成，2 条文本").wait_for()

        manual_button = page.get_by_role("button", name="手动翻译")
        _tab_to(page, manual_button)
        page.keyboard.press("Space")
        translations = page.locator("#manual-translations")
        _tab_to(page, translations)
        page.keyboard.insert_text("你好\n")

        save_button = page.get_by_role("button", name="保存并进入下一步")
        _tab_to(page, save_button)
        page.keyboard.press("Enter")

        dialog = page.get_by_role("dialog", name="确认空译文")
        dialog.wait_for()
        confirm_button = dialog.get_by_role("button", name="确认并保存")
        cancel_button = dialog.get_by_role("button", name="取消")
        expect(confirm_button).to_be_focused()

        # Initial focus starts on the primary action. Tab and Shift+Tab wrap
        # within the two dialog controls instead of escaping into the page.
        page.keyboard.press("Tab")
        expect(cancel_button).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(confirm_button).to_be_focused()

        # Escape closes without saving and restores focus to the exact trigger.
        page.keyboard.press("Escape")
        expect(dialog).to_be_hidden()
        expect(save_button).to_be_focused()

        # Reopen and finish the whole path using Enter only.
        page.keyboard.press("Enter")
        dialog.wait_for()
        expect(confirm_button).to_be_focused()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="导出").wait_for()

        export_button = page.get_by_role("button", name="生成输出文件")
        expect(export_button).to_be_enabled()
        _tab_to(page, export_button)
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        export_errors = [
            text
            for text in page.locator('[role="alert"]').all_text_contents()
            if text.strip()
        ]
        assert not export_errors, export_errors
        page.get_by_text("原文-译文对照版", exact=True).wait_for()
        browser.close()


def test_gui_task_list_failure_persists_until_retry(gui_server):
    """A failed resource load remains explicit, then a real retry recovers."""
    from playwright.sync_api import expect, sync_playwright

    attempts = 0

    def fail_first_jobs_request(route) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            route.abort("failed")
        else:
            route.continue_()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(_chromium_path()),
        )
        page = browser.new_page(viewport={"width": 900, "height": 700})
        page.route("**/api/jobs", fail_first_jobs_request)
        page.goto(gui_server, wait_until="networkidle")

        failure = page.get_by_role("alert").filter(
            has_text="任务列表加载失败"
        )
        failure.wait_for()
        expect(failure).to_be_visible()
        expect(page.get_by_text("暂无任务，输入文件路径新建一个")).to_be_hidden()

        # The recovery card is durable state, unlike the transient toast.
        # Keep the card visible beyond the three-second toast lifetime to prove
        # that it is durable resource state rather than a transient message.
        page.wait_for_timeout(3200)
        expect(failure).to_be_visible()
        assert attempts == 1

        retry_button = failure.get_by_role("button", name="重试")
        _tab_to(page, retry_button)
        page.keyboard.press("Enter")
        page.get_by_text("暂无任务，输入文件路径新建一个").wait_for()
        expect(failure).to_be_hidden()
        assert attempts == 2
        browser.close()


def test_gui_rich_text_policy_defaults_to_flatten_and_can_preserve(gui_server):
    """The default translates rich text, with an explicit preserve option."""
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(_chromium_path()),
        )
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.goto(gui_server, wait_until="networkidle")
        _create_browser_job(
            page,
            gui_server,
            "rich_text_workflow",
            workbook=_rich_workbook_bytes(),
        )
        page.reload(wait_until="networkidle")

        page.locator("button.job-select").filter(has_text="rich_text_workflow").click()
        page.get_by_role("button", name="开始提取").click()
        page.get_by_text("提取完成，1 条文本").wait_for()
        page.get_by_role("button", name="手动翻译").click()
        page.locator("#manual-translations").fill("你好世界")
        page.get_by_role("button", name="保存并进入下一步").click()
        page.get_by_role("heading", name="导出").wait_for()

        page.get_by_role("button", name="生成输出文件").click()
        page.get_by_text("仅译文版", exact=True).wait_for()
        page.get_by_text("原文-译文对照版", exact=True).wait_for()

        page.get_by_role("button", name="选择处理方式").click()
        dialog = page.get_by_role("dialog", name="选择富文本处理方式")
        dialog.wait_for()
        dialog.get_by_role("radio", name="保留受影响单元格的原文").check()
        dialog.get_by_role("button", name="保存处理方式").click()

        page.get_by_role("button", name="生成输出文件").click()
        page.get_by_text("仅译文版", exact=True).wait_for()
        page.get_by_text("原文-译文对照版", exact=True).wait_for()
        browser.close()


def test_gui_review_shows_row_diffs_and_only_changes_selected_rows(gui_server):
    """A grouped term review exposes per-row diffs and persists the chosen scope."""
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=str(_chromium_path()),
        )
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        page.goto(gui_server, wait_until="networkidle")
        _create_browser_job(page, gui_server, "review_scope")
        extracted_response = page.request.post(
            f"{gui_server}/api/jobs/review_scope/extract"
        )
        assert extracted_response.ok
        extracted = extracted_response.json()
        saved = page.request.post(
            f"{gui_server}/api/jobs/review_scope/ai_output",
            data={
                "source_revision": extracted["source_revision"],
                "results": [
                    {
                        "id": 0,
                        "translation": "API 调用",
                        "status": "succeeded",
                        "uncertain_terms": [
                            {
                                "term": "API",
                                "reason": "术语",
                                "candidate": "应用程序接口",
                            }
                        ],
                    },
                    {
                        "id": 1,
                        "translation": "API 文档",
                        "status": "succeeded",
                        "uncertain_terms": [
                            {
                                "term": "API",
                                "reason": "术语",
                                "candidate": "应用程序接口",
                            }
                        ],
                    },
                ],
                "summary": {
                    "status": "succeeded",
                    "total": 2,
                    "succeeded": 2,
                    "failed": 0,
                    "cancelled": 0,
                    "succeeded_ids": [0, 1],
                    "failed_ids": [],
                    "cancelled_ids": [],
                },
            },
        )
        assert saved.ok

        page.reload(wait_until="networkidle")
        page.locator("button.job-select").filter(has_text="review_scope").click()
        page.get_by_role("heading", name="审核与确认").wait_for()
        expect(page.get_by_text("逐行差异 · 选择要修改的行")).to_be_visible()

        choices = page.locator(".review-row-choice input[type=checkbox]")
        expect(choices).to_have_count(2)
        expect(choices.nth(0)).to_be_checked()
        expect(choices.nth(1)).to_be_checked()
        choices.nth(0).uncheck()

        page.locator("input[id^=review-target-]").fill("接口")
        expect(page.locator(".ctx-tgt.proposed")).to_have_count(1)
        expect(page.locator(".ctx-tgt.proposed")).to_contain_text("接口 文档")
        page.get_by_role("button", name="接受并入库").click()
        page.wait_for_timeout(800)
        visible_errors = [
            text
            for text in page.locator('[role="alert"]').all_text_contents()
            if text.strip()
        ]
        assert not visible_errors, visible_errors
        history = page.locator(".review-history")
        assert history.count() == 1, page.locator("body").inner_text()
        expect(history).to_be_visible()
        expect(history.get_by_text("已处理（1）")).to_be_visible()

        output = page.request.get(f"{gui_server}/api/jobs/review_scope/ai_output")
        assert output.ok
        assert [item["translation"] for item in output.json()["results"]] == [
            "API 调用",
            "接口 文档",
        ]
        review = page.request.get(
            f"{gui_server}/api/jobs/review_scope/review",
            params={"source_revision": extracted["source_revision"]},
        )
        assert review.ok
        assert review.json()["items"][0]["selected_row_ids"] == [1]
        browser.close()
