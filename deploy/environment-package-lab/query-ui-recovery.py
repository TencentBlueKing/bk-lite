from pathlib import Path
from query_run import verified_run, find_alert_row
import json, re
from playwright.sync_api import sync_playwright, expect

root = Path("/test")
out = root / "evidence/query-alert-20261115"
out.mkdir(exist_ok=True)
login = json.loads((root / "config/ui-login.json").read_text())
url = "http://10.10.248.31:18300"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    c = b.new_context(timezone_id="Asia/Shanghai", viewport={"width": 1440, "height": 1000})
    page = c.new_page()
    page.goto(url + "/auth/signin", wait_until="networkidle")
    page.locator('input[autocomplete="username"]').fill(login["username"])
    page.locator('input[autocomplete="current-password"]').fill(login["password"])
    page.locator('button[type="submit"]').click()
    page.wait_for_url(lambda u: "/auth/signin" not in u, timeout=60000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    current = verified_run(out)
    checks = []
    for kind, route, status in [("apm", "/apm/events/alerts", "已恢复"), ("log", "/log/event/alert", "关闭")]:
        for alert in current["alerts"][kind]:
            page.goto(url + route, wait_until="networkidle")
            page.get_by_role("tab", name=re.compile("历史")).click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1000)
            row = find_alert_row(page, alert["id"])
            expect(row).to_have_count(1)
            if kind == "log":
                expect(row).to_contain_text(status)
            expect(row).to_contain_text("已通知")
            row.get_by_role("button", name="详情", exact=True).click()
            detail = page.get_by_role("dialog")
            expect(detail).to_be_visible()
            expect(detail).to_contain_text(status)
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / (kind + "-recovered-" + alert["id"] + ".png")), full_page=True)
            checks.append({"kind": kind, "alert_id": alert["id"], "status": status, "notified": True})
    (out / "ui-recovery-checks.json").write_text(json.dumps({"run_id": current["run_id"], "checks": checks}, ensure_ascii=False, indent=2))
    b.close()
    print("__RECOVERY_HISTORY_UI_PASSED__")
