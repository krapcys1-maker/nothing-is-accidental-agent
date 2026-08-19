"""Rozstrzygajacy test: czy sesja zalozona NA SERWERZE przepuszcza publikacje."""
from playwright.sync_api import sync_playwright

zapisy = []

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://localhost:9222")
    ctx = b.contexts[0]
    nazwy = {c["name"] for c in ctx.cookies()}
    print("substack.sid:", "substack.sid" in nazwy)
    print("cf_clearance:", "cf_clearance" in nazwy)

    if "substack.sid" in nazwy:
        ctx.storage_state(path="agent-v2/data/storage-state-serwer.json")
        print("sesja serwerowa zapisana")

    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.on("response", lambda r: zapisy.append(
        (r.status, r.request.method)) if "/comment/feed" in r.url else None)

    pg.goto("https://substack.com/home", wait_until="domcontentloaded",
            timeout=60_000)
    pg.wait_for_timeout(6000)
    print("strona:", len(pg.inner_text("body")), "znakow")

    pg.locator("[class*=Composer]").first.click(timeout=20_000)
    pg.wait_for_timeout(3000)
    pg.locator("[contenteditable=true]").first.click()
    pg.keyboard.type("Server publish check.", delay=30)
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Post").first.click()
    pg.wait_for_timeout(12_000)

    print("odpowiedz na publikacje:", zapisy or "brak zapytania")
    if any(s == 200 for s, _ in zapisy):
        print("\n  UDALO SIE — PUBLIKACJA Z SERWERA DZIALA")
    else:
        print("\n  nadal blokowane")
    b.close()
