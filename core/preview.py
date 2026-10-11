"""Slide previews: a built deck rendered to a PDF and one PNG per slide, so the Team brief page can show the
slides and offer a PDF next to the .pptx. Needs LibreOffice (soffice) for the PDF and poppler (pdftoppm) for the
page images; without them the page shows the slide outline and the .pptx only."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def available() -> dict:
    return {"soffice": bool(shutil.which("soffice")), "pdftoppm": bool(shutil.which("pdftoppm"))}


def render_pdf(pptx: str | Path, out_dir: str | Path, timeout: int = 120) -> tuple[str, str]:
    """The deck as <out_dir>/deck.pdf. Returns (pdf path or "", why not)."""
    pptx, out_dir = Path(pptx), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not available()["soffice"]:
        return "", "LibreOffice (soffice) is not installed on this server"
    pdf = out_dir / "deck.pdf"
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile:
        env = {**os.environ, "SAL_USE_VCLPLUGIN": "svp", "HOME": profile}
        cmd = ["soffice", f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--convert-to", "pdf",
               "--outdir", str(out_dir), str(pptx)]
        try:
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"pdf": "", "pages": [], "why": f"PDF conversion failed: {e}"}
    made = out_dir / (pptx.stem + ".pdf")
    if not made.exists():
        return "", "PDF conversion failed: " + (r.stderr or r.stdout).strip()[-300:]
    if made != pdf:
        made.replace(pdf)
    for old in out_dir.glob("slide-*.png"):  # pages of the deck this one replaces
        old.unlink()
    return str(pdf), ""


def page_count(pdf: str | Path) -> int:
    try:
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=30)
        m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
        return int(m.group(1)) if m else 0
    except (OSError, subprocess.TimeoutExpired):
        return 0


def render_page(pdf: str | Path, n: int, out_dir: str | Path, dpi: int = 96, timeout: int = 60) -> str:
    """One page (1-based) of the PDF as <out_dir>/slide-<n>.png, so a preview can fill in slide by slide.
    Returns the image path, or "" without poppler."""
    pdf, out_dir = Path(pdf), Path(out_dir)
    if not available()["pdftoppm"]:
        return ""
    stem = out_dir / f"slide-{n}"
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(n), "-l", str(n), "-singlefile", str(pdf), str(stem)],
                   capture_output=True, timeout=timeout)
    return str(stem.with_suffix(".png")) if stem.with_suffix(".png").exists() else ""


def render(pptx: str | Path, out_dir: str | Path, timeout: int = 120, dpi: int = 96, on_page=None) -> dict:
    """Writes <out_dir>/deck.pdf and <out_dir>/slide-1.png ... `on_page(n, total, path)` is called as each page
    lands. Returns {"pdf": path or "", "pages": [paths], "why": ""}."""
    pdf, why = render_pdf(pptx, out_dir, timeout)
    if not pdf:
        return {"pdf": "", "pages": [], "why": why}
    pages = []
    total = page_count(pdf)
    for n in range(1, total + 1):
        if (p := render_page(pdf, n, out_dir, dpi)):
            pages.append(p)
            if on_page:
                on_page(n, total, p)
        else:
            break
    return {"pdf": pdf, "pages": pages, "why": "" if pages else "page images need poppler (pdftoppm)"}
