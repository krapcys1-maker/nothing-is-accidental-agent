"""Regresja granicy pobierania: żaden słabszy transport nie omija safe_fetch."""

import inspect
import pathlib
import sys

sys.path.insert(0, "agent-v3")
import browser  # noqa: E402
import config  # noqa: E402
import safe_fetch  # noqa: E402
import stages  # noqa: E402


zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. FETCH UŻYWA WYŁĄCZNIE CENTRALNEGO ADAPTERA ===")
src = inspect.getsource(stages.fetch)
sprawdz("fetch woła safe_fetch.get", "safe_fetch.get(" in src)
sprawdz("fetch nie tworzy surowego klienta HTTPX", "httpx.Client" not in src)
sprawdz("fetch nie włącza automatycznych redirectów", "follow_redirects" not in src)
sprawdz("zapisuje finalny URL", '"url": final_url' in src)
sprawdz("zapisuje IP", "resolved_ips_json" in src)
sprawdz("zapisuje ID wersji dokumentu", "document_id" in src and "content_sha256" in src)

print()
print("=== 2. FALLBACK PRZEGLĄDARKOWY JEST FAIL-CLOSED ===")
sprawdz("pusta lista pozostaje pusta",
        stages._dobierz_przegladarka(None, 1, [], []) == [])
sprawdz("lista stron NIE otwiera przeglądarki",
        stages._dobierz_przegladarka(
            None, 1, [{"url": "https://example.com/a"}], []) == [])

read_src = inspect.getsource(browser.read_pages)
wykonywalne = read_src.split('"""')[-1]
sprawdz("read_pages nie ma page.goto", "page.goto" not in wykonywalne)
sprawdz("read_pages jawnie odmawia", "raise RuntimeError" in wykonywalne)

oryg = browser.capabilities.require
try:
    browser.capabilities.require = lambda *_args, **_kwargs: None
    try:
        browser.read_pages(["https://example.com/a"])
        odmowa = False
    except RuntimeError:
        odmowa = True
    sprawdz("stare wywołanie kończy się odmową", odmowa)
finally:
    browser.capabilities.require = oryg

print()
print("=== 3. LIMITY I DNS SĄ TWARDE ===")
sprawdz("JSON ma osobny limit",
        config.FETCH_MAX_JSON_BYTES < config.FETCH_MAX_HTML_BYTES)
sprawdz("PDF ma osobny większy limit",
        config.FETCH_MAX_PDF_BYTES > config.FETCH_MAX_HTML_BYTES)
sprawdz("tekst po parserze też ma limit", config.FETCH_MAX_EXTRACTED_CHARS > 0)
pdf_src = inspect.getsource(stages._tekst_z_pdf)
sprawdz("parser PDF ogranicza rozpakowany strumień",
        "FETCH_MAX_PDF_DECOMPRESSED_STREAM_BYTES" in pdf_src)
safe_src = pathlib.Path(safe_fetch.__file__).read_text(encoding="utf-8")
sprawdz("transport wyłącza proxy środowiskowe", "trust_env=False" in safe_src)
sprawdz("połączenie używa PinnedDNSBackend", "network_backend=PinnedDNSBackend" in safe_src)

print()
print("=== WYNIK: %s zdanych, %s oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
