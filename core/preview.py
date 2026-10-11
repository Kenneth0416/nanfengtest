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


def render(pptx: str | Path, out_dir: str | Path, timeout: int = 120) -> dict:
    """Writes <out_dir>/deck.pdf and <out_dir>/slide-01.png ... Returns {"pdf": path or "", "pages": [paths], "why": ""}."""
    pptx, out_dir = Path(pptx), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    have = available()
    if not have["soffice"]:
        return {"pdf": "", "pages": [], "why": "LibreOffice (soffice) is not installed on this server"}
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
        return {"pdf": "", "pages": [], "why": "PDF conversion failed: " + (r.stderr or r.stdout).strip()[-300:]}
    if made != pdf:
        made.replace(pdf)
    pages = []
    if have["pdftoppm"]:
        for old in out_dir.glob("slide-*.png"):
            old.unlink()
        subprocess.run(["pdftoppm", "-png", "-r", "60", str(pdf), str(out_dir / "slide")], capture_output=True, timeout=timeout)
        pages = [str(p) for p in sorted(out_dir.glob("slide-*.png"), key=lambda q: int(re.sub(r"\D", "", q.stem) or 0))]
    return {"pdf": str(pdf), "pages": pages, "why": "" if pages else "page images need poppler (pdftoppm)"}
