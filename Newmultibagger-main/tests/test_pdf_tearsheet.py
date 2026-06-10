"""
tests/test_pdf_tearsheet.py
============================
Unit + integration tests for Item 2: PDF Tearsheets.

Run with:
    pytest tests/test_pdf_tearsheet.py -v

All filesystem / WeasyPrint / HTML-generation side effects are mocked so these
tests run without any live market data, WeasyPrint install, or web-ui directory.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_html(tmp_path: Path, symbol_bare: str) -> Path:
    """Write a minimal HTML file in the expected reports directory."""
    reports_dir = tmp_path / "web-ui" / "reports"
    reports_dir.mkdir(parents=True)
    html = reports_dir / f"{symbol_bare}.html"
    html.write_text(
        "<html><head></head><body><h1>Test</h1></body></html>",
        encoding="utf-8",
    )
    return html


def _patch_paths(monkeypatch, tmp_path: Path, module):
    """Redirect the module-level path constants to tmp_path."""
    monkeypatch.setattr(module, "_REPORTS_DIR", tmp_path / "web-ui" / "reports")
    monkeypatch.setattr(module, "_PDF_DIR", tmp_path / "web-ui" / "reports" / "pdf")


# ---------------------------------------------------------------------------
# 1. WeasyPrint not installed → RuntimeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weasyprint_missing_raises_runtime_error(tmp_path, monkeypatch):
    """generate_pdf_tearsheet must raise RuntimeError when WeasyPrint is absent."""
    # Ensure weasyprint is NOT importable for this test
    monkeypatch.setitem(sys.modules, "weasyprint", None)  # type: ignore[arg-type]

    # Re-import module so it picks up the patched sys.modules
    if "modules.reporting.pdf_tearsheet" in sys.modules:
        del sys.modules["modules.reporting.pdf_tearsheet"]

    with pytest.raises(RuntimeError, match="WeasyPrint is not installed"):
        # We need to call the function; patch paths so it doesn't hit real FS
        import modules.reporting.pdf_tearsheet as ts
        _patch_paths(monkeypatch, tmp_path, ts)
        await ts.generate_pdf_tearsheet("PFC.NS")


# ---------------------------------------------------------------------------
# 2. HTML does not exist → html_report.generate_premium_html_report is called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_html_triggers_generation(tmp_path, monkeypatch):
    """
    When the HTML file is absent, the module must call generate_premium_html_report
    before proceeding.
    """
    # Provide a fake weasyprint
    fake_wp = MagicMock()
    fake_doc = MagicMock()
    fake_doc.write_pdf = MagicMock()
    fake_wp.HTML.return_value = fake_doc
    fake_wp.CSS = MagicMock()
    monkeypatch.setitem(sys.modules, "weasyprint", fake_wp)

    if "modules.reporting.pdf_tearsheet" in sys.modules:
        del sys.modules["modules.reporting.pdf_tearsheet"]

    import modules.reporting.pdf_tearsheet as ts
    _patch_paths(monkeypatch, tmp_path, ts)

    # Create the HTML file only inside the mock (simulates generation)
    html_file = tmp_path / "web-ui" / "reports" / "PFC.html"

    async def _fake_generate(symbol):
        html_file.parent.mkdir(parents=True, exist_ok=True)
        html_file.write_text("<html><head></head><body>Generated</body></html>")
        return str(html_file)

    # Also create PDF dir so write_pdf path exists
    pdf_dir = tmp_path / "web-ui" / "reports" / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # Patch write_pdf to actually create the file
    def _fake_write_pdf(path):
        Path(path).write_bytes(b"%PDF-fake")

    fake_doc.write_pdf.side_effect = _fake_write_pdf

    import modules.reporting.html_report
    with patch(
        "modules.reporting.html_report.generate_premium_html_report",
        side_effect=_fake_generate,
    ) as mock_gen, patch(
        "modules.symbol_utils.normalize_symbol",
        side_effect=lambda s: s if "." in s else s + ".NS",
    ):
        result = await ts.generate_pdf_tearsheet("PFC")

    mock_gen.assert_called_once_with("PFC.NS")
    assert result.endswith(".pdf")


# ---------------------------------------------------------------------------
# 3. PDF cache hit → WeasyPrint render NOT called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_cache_hit_skips_render(tmp_path, monkeypatch):
    """
    When a fresh PDF already exists (mtime >= HTML mtime), WeasyPrint must NOT
    be called again.
    """
    fake_wp = MagicMock()
    monkeypatch.setitem(sys.modules, "weasyprint", fake_wp)

    if "modules.reporting.pdf_tearsheet" in sys.modules:
        del sys.modules["modules.reporting.pdf_tearsheet"]

    import modules.reporting.pdf_tearsheet as ts
    _patch_paths(monkeypatch, tmp_path, ts)

    # Write HTML
    html_file = _make_dummy_html(tmp_path, "RELIANCE")
    # Write PDF with mtime newer than HTML
    pdf_dir = tmp_path / "web-ui" / "reports" / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = pdf_dir / "RELIANCE_tearsheet.pdf"
    pdf_file.write_bytes(b"%PDF-cached")

    # Force PDF mtime to be after HTML mtime
    import os, time
    os.utime(str(pdf_file), (time.time() + 10, time.time() + 10))

    with patch(
        "modules.symbol_utils.normalize_symbol",
        side_effect=lambda s: s if "." in s else s + ".NS",
    ):
        result = await ts.generate_pdf_tearsheet("RELIANCE.NS")

    fake_wp.HTML.assert_not_called()
    assert "RELIANCE_tearsheet.pdf" in result


# ---------------------------------------------------------------------------
# 4. PDF stale → WeasyPrint IS called; file created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stale_pdf_triggers_render(tmp_path, monkeypatch):
    """
    When the HTML is newer than the existing PDF, WeasyPrint must re-render.
    """
    import time, os

    fake_wp = MagicMock()
    fake_doc = MagicMock()
    fake_wp.HTML.return_value = fake_doc
    fake_wp.CSS = MagicMock()
    monkeypatch.setitem(sys.modules, "weasyprint", fake_wp)

    if "modules.reporting.pdf_tearsheet" in sys.modules:
        del sys.modules["modules.reporting.pdf_tearsheet"]

    import modules.reporting.pdf_tearsheet as ts
    _patch_paths(monkeypatch, tmp_path, ts)

    # Write HTML (mtime = now)
    html_file = _make_dummy_html(tmp_path, "INFY")

    # Write STALE PDF (mtime = 60 s ago)
    pdf_dir = tmp_path / "web-ui" / "reports" / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = pdf_dir / "INFY_tearsheet.pdf"
    pdf_file.write_bytes(b"%PDF-stale")
    os.utime(str(pdf_file), (time.time() - 60, time.time() - 60))
    # HTML is newer (touch it again)
    os.utime(str(html_file), (time.time() + 1, time.time() + 1))

    def _fake_write_pdf(path):
        Path(path).write_bytes(b"%PDF-fresh")

    fake_doc.write_pdf.side_effect = _fake_write_pdf

    with patch(
        "modules.symbol_utils.normalize_symbol",
        side_effect=lambda s: s if "." in s else s + ".NS",
    ):
        result = await ts.generate_pdf_tearsheet("INFY.NS")

    fake_wp.HTML.assert_called_once()
    fake_doc.write_pdf.assert_called_once()
    assert "INFY_tearsheet.pdf" in result


# ---------------------------------------------------------------------------
# 5. FastAPI route — 503 when WeasyPrint absent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_route_returns_503_when_weasyprint_missing():
    """
    The GET /api/reports/pdf/{symbol} route must return 503 when
    generate_pdf_tearsheet raises RuntimeError (WeasyPrint not installed).
    """
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from app_routes.public import router

    app = FastAPI()
    app.include_router(router)

    async def _mock_pdf_gen(symbol):
        raise RuntimeError("WeasyPrint is not installed.")

    with patch(
        # normalize_symbol is imported at module level in public.py
        # → patch at the call site in that module.
        "app_routes.public.normalize_symbol", side_effect=lambda s: s + ".NS"
    ), patch(
        # The route does: from modules.reporting.pdf_tearsheet import generate_pdf_tearsheet
        # inside the function body → Python binds the name in that local scope each call,
        # so we must patch the source function at its defining module.
        "modules.reporting.pdf_tearsheet.generate_pdf_tearsheet",
        side_effect=_mock_pdf_gen,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/reports/pdf/TESTSTOCK",
                headers={"X-API-Key": "test"},
            )

    assert resp.status_code == 503
    assert "WeasyPrint" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 6. FastAPI route — 200 + correct Content-Disposition on success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_route_returns_200_with_file(tmp_path):
    """
    A successful PDF generation must return 200 with application/pdf and
    the correct Content-Disposition attachment filename.
    """
    from httpx import AsyncClient, ASGITransport
    from fastapi import FastAPI
    from app_routes.public import router

    # Create a real dummy PDF file
    pdf_file = tmp_path / "HDFC_tearsheet.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    app = FastAPI()
    app.include_router(router)

    async def _mock_pdf_gen(symbol):
        return str(pdf_file)

    with patch(
        "app_routes.public.normalize_symbol", side_effect=lambda s: "HDFC.NS"
    ), patch(
        "modules.reporting.pdf_tearsheet.generate_pdf_tearsheet",
        side_effect=_mock_pdf_gen,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/reports/pdf/HDFC",
                headers={"X-API-Key": "test"},
            )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "HDFC_tearsheet.pdf" in resp.headers.get("content-disposition", "")
