"""Browser test of the page exactly as GitHub Pages serves it.

docs/ is copied to a temporary folder, the publish placeholders are filled
the way the release script fills them, and the copy is served under
/cement-calc/ on localhost. Headless Chromium then runs the main workflows and
fails on any page error, console error or Content-Security-Policy violation.

Needs the playwright package and its Chromium; skipped when they are missing.
"""

import functools
import http.server
import shutil
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
NAME = "cement-calc"
FILL = {
    "https://wjwhitmire.github.io/cement-calc/": f"https://wjwhitmire.github.io/{NAME}/",
    "wjwhitmire": "wjwhitmire",
    "https://github.com/wjwhitmire/cement-calc": f"https://github.com/wjwhitmire/{NAME}",
}
WATCH = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("pages")
    dest = root / NAME
    shutil.copytree(ROOT / "docs", dest)
    for f in dest.rglob("*"):
        if f.suffix in (".html", ".js", ".json", ".webmanifest", ".css", ".txt", ".xml"):
            text = f.read_text(encoding="utf-8")
            for k, v in FILL.items():
                text = text.replace(k, v)
            f.write_text(text, encoding="utf-8")
    handler = functools.partial(QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/{NAME}/"
    server.shutdown()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def open_page(browser, url, width=1280, **ctx):
    context = browser.new_context(viewport={"width": width, "height": 900}, **ctx)
    context.route("https://fonts.googleapis.com/**", lambda r: r.abort())
    context.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    context.add_init_script(WATCH)
    page = context.new_page()
    page.problems = []
    page.on("pageerror", lambda e: page.problems.append(f"pageerror: {e}"))
    page.on(
        "console",
        lambda m: page.problems.append(f"console: {m.text}")
        if m.type == "error" and "fonts.g" not in m.text and "ERR_FAILED" not in m.text
        and not (m.location or {}).get("url", "").endswith("/favicon.ico")
        else None,
    )
    page.goto(url)
    return page


def assert_clean(page):
    csp = page.evaluate("window.__csp")
    assert not csp, csp
    assert not page.problems, page.problems
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    for placeholder in FILL:
        assert placeholder not in page.content()


PRIMARY_CSV = (ROOT / "examples" / "primary.csv").read_text()


def status(page, prefix="p"):
    return page.text_content(f"#{prefix}-status")


def edit(page, box, value):
    page.fill(f"#{box}", value)
    page.wait_for_timeout(50)


def test_primary_example(site, browser):
    page = open_page(browser, site)
    assert "Inputs valid" in status(page)
    tiles = page.text_content("#p-tiles")
    assert "715" in tiles and "1,302" in tiles and "346.9" in tiles
    assert_clean(page)


def test_plug_tab(site, browser):
    page = open_page(browser, site)
    page.click("#tab-plug")
    tiles = page.text_content("#b-tiles")
    assert "44.6" in tiles and "237" in tiles and "60.9" in tiles
    assert_clean(page)


def test_error_uses_labels_and_disables_copy(site, browser):
    page = open_page(browser, site)
    edit(page, "p-lead_density_ppg", "0")
    s = status(page)
    assert "Lead slurry density must be between 0 and 30 ppg" in s
    assert page.get_attribute("#p-lead_density_ppg", "aria-invalid") == "true"
    assert page.is_disabled("#p-copy")
    edit(page, "p-spacer_bbl", "-1")
    edit(page, "p-lead_density_ppg", "11.5")
    assert page.get_attribute("#p-spacer_bbl", "aria-invalid") == "true"
    edit(page, "p-spacer_bbl", "40")
    assert page.is_enabled("#p-copy")


def test_decimal_comma_file_is_refused(site, browser, tmp_path):
    f = tmp_path / "job.csv"
    f.write_text(PRIMARY_CSV.replace("lead_density_ppg,11.5", "lead_density_ppg,11,5"))
    page = open_page(browser, site)
    page.set_input_files("#p-file", str(f))
    page.wait_for_function("document.getElementById('p-status').textContent.includes('split by a comma')")


def test_file_without_tvds_is_read_as_vertical(site, browser, tmp_path):
    lines = [ln for ln in PRIMARY_CSV.splitlines() if not ln.startswith("tvd")]
    f = tmp_path / "job.csv"
    f.write_text("\n".join(lines) + "\n")
    page = open_page(browser, site)
    page.set_input_files("#p-file", str(f))
    page.wait_for_function("document.getElementById('p-status').textContent.includes('TVD = MD')")
    assert page.is_checked("#p-tvd_equals_md")
    assert "Inputs valid" in status(page)


def test_plug_file_switches_tab_and_copy(site, browser, tmp_path):
    f = tmp_path / "plug.json"
    f.write_text((ROOT / "examples" / "plug.json").read_text())
    page = open_page(browser, site)
    page.set_input_files("#p-file", str(f))
    page.wait_for_function("document.getElementById('tab-plug').getAttribute('aria-selected') === 'true'")
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
    page.click("#b-copy")
    assert len(page.input_value("#b-fallback")) > 50


def test_phone_width(site, browser):
    page = open_page(browser, site, width=400, has_touch=True, is_mobile=True)
    assert "Inputs valid" in status(page)
    assert_clean(page)


def test_implausible_values(site, browser):
    page = open_page(browser, site)
    edit(page, "p-tail_yield_ft3_sk", "0.3")
    assert "Tail slurry yield must be between 0.5 and 15" in status(page)
    assert page.get_attribute("#p-tail_yield_ft3_sk", "aria-invalid") == "true"
    edit(page, "p-tail_yield_ft3_sk", "1.27")
    edit(page, "p-lead_density_ppg", "9")
    assert "Inputs valid" in status(page)
    assert "Lead density 9 ppg is outside the usual 11 to 19 ppg" in page.text_content("#p-chips")
