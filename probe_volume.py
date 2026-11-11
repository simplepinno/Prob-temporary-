#!/usr/bin/env python3
"""DSE volume page PROBE (read-only, no login). Writes nothing but diagnostics.

Opens https://dse.co.tz/en/all-equities, then for each tab (Value, Volume,
Gainers, Losers) and for "Show all securities" saves the page text, a
screenshot, any HTML table rows, and the list of data (xhr/fetch) calls the
page itself makes. Output goes to probe/. Run it once, look at the files,
then we write the real scraper.
"""
import json
import os
import re
import time
from pathlib import Path

URL = os.getenv("DSE_URL", "https://dse.co.tz/en/all-equities")
OUT = Path(os.getenv("PROBE_DIR", "probe"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def snap(page, name):
    (OUT / f"{name}.txt").write_text(page.inner_text("body"), encoding="utf-8")
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print(f"saved {name}")


def click_text(page, label):
    loc = page.get_by_text(re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
    for i in range(loc.count()):
        el = loc.nth(i)
        try:
            if not el.is_visible():
                continue
            el.scroll_into_view_if_needed()
            try:
                el.click(timeout=2000)
            except Exception:  # noqa: BLE001
                try:  # something overlaps it: force the click
                    el.click(timeout=2000, force=True)
                except Exception:  # noqa: BLE001
                    el.evaluate("e => e.click()")  # last resort: JS click
            time.sleep(2)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"WARN: click '{label}' failed: {str(e)[:120]}")
    print(f"WARN: '{label}' not found/clickable")
    return False


def dump_tables(page, name):
    data = page.evaluate("""() => [...document.querySelectorAll('table')].map(t => ({
        headers: [...t.querySelectorAll('th')].map(h => h.innerText.trim()),
        rows: [...t.querySelectorAll('tr')].map(r =>
            [...r.querySelectorAll('td')].map(c => c.innerText.trim().replace(/\\s+/g,' ')))
            .filter(r => r.length)
    }))""")
    (OUT / f"{name}_tables.json").write_text(
        json.dumps(data, indent=1), encoding="utf-8")
    for i, t in enumerate(data):
        print(f"{name}: table {i}: {len(t['rows'])} rows, headers={t['headers']}")
    if not data:
        print(f"{name}: no <table> elements (layout is probably div-based)")


def main():
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    seen = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  user_agent=UA, locale="en-US",
                                  timezone_id="Africa/Dar_es_Salaam")
        page = ctx.new_page()
        page.on("response", lambda r: seen.append(r)
                if r.request.resource_type in ("xhr", "fetch") else None)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)
        snap(page, "00_initial")
        for i, tab in enumerate(["Value", "Volume", "Gainers", "Losers"], 1):
            if click_text(page, tab):
                snap(page, f"0{i}_tab_{tab.lower()}")
        if click_text(page, "Show all securities"):
            time.sleep(2)
            snap(page, "10_show_all")
            (OUT / "10_show_all.html").write_text(page.content(), encoding="utf-8")
            dump_tables(page, "10_show_all")
        # what the page itself fetched
        calls = []
        for n, r in enumerate(seen):
            try:
                ct = r.headers.get("content-type", "")
                calls.append(f"{r.status} {r.request.method} {r.url} [{ct}]")
                if "json" in ct:
                    body = r.text()[:200000]
                    (OUT / f"api_{n:02d}.json").write_text(body, encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                calls.append(f"? {r.url} ({e})")
        (OUT / "api_calls.txt").write_text("\n".join(calls), encoding="utf-8")
        print("data calls the page made:")
        print("\n".join(calls) or "none")
        browser.close()


if __name__ == "__main__":
    main()
