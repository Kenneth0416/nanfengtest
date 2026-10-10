"""Builds the sample upload used in the demo.

The figures are restated from BNP Paribas Real Estate's public article
"Central London office market update Q2 2025"
(https://www.realestate.bnpparibas.co.uk/insights/central-london-office-market-update-q2-2025).
This is a test input for the PoC, not a BNP Paribas document.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).with_name("sample_bnp_paribas_q2_2025_restated.pdf")
LINES = [
    ("h", "Central London Office Market Update - Q2 2025"),
    ("p", "Figures restated from BNP Paribas Real Estate's public Q2 2025 market update"),
    ("p", "PoC test input only - not an official BNP Paribas document."),
    ("", ""),
    ("h", "Central London"),
    ("p", "Take-up: 3.20m sq ft"),
    ("p", "Availability: 23.98m sq ft"),
    ("p", "Vacancy rate: 8.3%"),
    ("", ""),
    ("h", "West End"),
    ("p", "Prime rent: £170 psf"),
    ("p", "Vacancy rate: 6.4%"),
    ("", ""),
    ("h", "City"),
    ("p", "Prime rent: £87.50 psf"),
    ("p", "Vacancy rate: 9.1%"),
]


def build():
    c = canvas.Canvas(str(OUT), pagesize=A4)
    y = 800
    for kind, text in LINES:
        c.setFont("Helvetica-Bold" if kind == "h" else "Helvetica", 14 if kind == "h" else 11)
        c.drawString(60, y, text)
        y -= 22 if kind else 10
    c.save()
    return OUT


if __name__ == "__main__":
    print(build())
