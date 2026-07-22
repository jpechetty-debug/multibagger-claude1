"""
modules/reporting/pdf_tearsheet.py
===================================
Sovereign AI — PDF Tearsheet Generator (Item 2)

Converts the existing premium HTML audit report into a
print-optimised, single-page-wide PDF tearsheet using WeasyPrint.

Public API
----------
  generate_pdf_tearsheet(symbol: str) -> str
      Returns the absolute path to the generated PDF file.
      Raises RuntimeError on WeasyPrint import failure so the caller
      can return a helpful 503 instead of a raw 500.

Cache strategy
--------------
  PDFs are cached alongside HTMLs in web-ui/reports/ as
  {SYMBOL_WITHOUT_EXCHANGE}.pdf.
  They are regenerated whenever the underlying HTML is regenerated
  (checked by comparing mtime — HTML mtime must be newer than PDF mtime).

WeasyPrint install
------------------
  pip install weasyprint
  Ubuntu/Debian system deps: apt-get install libpango-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
  Already covered by the Docker image once you add `weasyprint` to requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

from core.observability.logger import get_logger

_log = get_logger("modules.reporting.pdf_tearsheet")

# ---------------------------------------------------------------------------
# Path constants (mirrors html_report.py)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parents[1]          # …/Newmultibagger-main/
_REPORTS_DIR = _PROJECT_ROOT / "web-ui" / "reports"
_PDF_DIR = _PROJECT_ROOT / "web-ui" / "reports" / "pdf"


def _ensure_dirs() -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _PDF_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# WeasyPrint CSS injected at PDF render time
# ---------------------------------------------------------------------------
# These @page rules are injected into the HTML before conversion so WeasyPrint
# produces a landscape A4 tearsheet with sensible margins.
_PAGE_CSS = """
@page {
    size: A4 landscape;
    margin: 12mm 10mm 12mm 10mm;
}
/* Remove interactive widgets that don't print well */
.no-print, nav, .nav-btn, button, .btn { display: none !important; }
/* Ensure full-width layout on paper */
body { font-size: 10pt; }
table { page-break-inside: avoid; }
"""

_STYLE_INJECTION = f"<style>{_PAGE_CSS}</style></head>"


def _html_path(symbol_bare: str) -> Path:
    """Return the path where html_report.py writes its output."""
    return _REPORTS_DIR / f"{symbol_bare}.html"


def _pdf_path(symbol_bare: str) -> Path:
    return _PDF_DIR / f"{symbol_bare}_tearsheet.pdf"


def _is_pdf_stale(html_path: Path, pdf_path: Path) -> bool:
    """Return True if PDF does not exist or HTML has been updated since last PDF render."""
    if not pdf_path.exists():
        return True
    return html_path.stat().st_mtime > pdf_path.stat().st_mtime


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

async def generate_pdf_tearsheet(symbol: str) -> str:
    """
    Generate a PDF tearsheet for *symbol*.

    Parameters
    ----------
    symbol:
        Raw ticker, e.g. ``"PFC.NS"`` or ``"RELIANCE"``.
        The function normalises exchange suffixes itself.

    Returns
    -------
    str
        Absolute path to the generated (or cached) PDF file.

    Raises
    ------
    RuntimeError
        If WeasyPrint is not installed — caller should surface this as HTTP 503.
    FileNotFoundError
        If the source HTML has not been generated yet — caller should trigger
        HTML generation first (``generate_premium_html_report``) then retry.
    """
    # ------------------------------------------------------------------
    # 0. WeasyPrint availability guard
    # ------------------------------------------------------------------
    try:
        from weasyprint import HTML as WPHtml  # noqa: N814
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint is not installed. "
            "Add `weasyprint` to requirements.txt and rebuild the container."
        ) from exc

    # ------------------------------------------------------------------
    # 1. Normalise symbol
    # ------------------------------------------------------------------
    from modules.symbol_utils import normalize_symbol
    symbol = normalize_symbol(symbol)
    symbol_bare = symbol.split(".")[0].upper()  # e.g. "PFC"

    _ensure_dirs()

    html_file = _html_path(symbol_bare)
    pdf_file = _pdf_path(symbol_bare)

    # ------------------------------------------------------------------
    # 2. Ensure HTML source exists (generate if needed)
    # ------------------------------------------------------------------
    if not html_file.exists():
        _log.info("HTML report missing — generating before PDF conversion", symbol=symbol)
        from modules.reporting.html_report import generate_premium_html_report
        result = await generate_premium_html_report(symbol)
        if not html_file.exists():
            raise FileNotFoundError(
                f"HTML report generation returned '{result}' but file not found at {html_file}"
            )

    # ------------------------------------------------------------------
    # 3. Cache hit: return existing PDF if HTML hasn't changed
    # ------------------------------------------------------------------
    if not _is_pdf_stale(html_file, pdf_file):
        _log.info("Returning cached PDF tearsheet", symbol=symbol, path=str(pdf_file))
        return str(pdf_file)

    # ------------------------------------------------------------------
    # 4. Inject print CSS and render via WeasyPrint
    # ------------------------------------------------------------------
    _log.info("Rendering PDF tearsheet", symbol=symbol, source_html=str(html_file))

    html_content = html_file.read_text(encoding="utf-8")

    # Inject @page CSS before </head> so WeasyPrint picks it up
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", _STYLE_INJECTION, 1)
    else:
        # Fallback: prepend style block
        html_content = f"<style>{_PAGE_CSS}</style>\n" + html_content

    # WeasyPrint resolves relative asset paths (fonts, images) against base_url
    base_url = html_file.parent.as_uri() + "/"

    try:
        doc = WPHtml(string=html_content, base_url=base_url)
        doc.write_pdf(str(pdf_file))
    except Exception as exc:
        _log.error("WeasyPrint PDF render failed", symbol=symbol, error=str(exc))
        raise

    _log.info(
        "PDF tearsheet generated",
        symbol=symbol,
        path=str(pdf_file),
        size_kb=round(pdf_file.stat().st_size / 1024, 1),
    )
    return str(pdf_file)
