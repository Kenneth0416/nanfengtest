"""Draws the sample 'photo' of a lease front page used by the Internal data demo and tests.
python reference/samples/make_sample_photo.py -> reference/samples/lease_front_page_8_bishopsgate.jpg"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).with_name("lease_front_page_8_bishopsgate.jpg")
W, H = 1240, 1650
img = Image.new("RGB", (W, H), (246, 243, 236))
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for name in (["DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"] if bold else ["DejaVuSerif.ttf"]):
        try:
            return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
        except OSError:
            pass
    return ImageFont.load_default()


y = 140
d.text((W / 2, y), "DATED 2 OCTOBER 2026", fill=(40, 40, 40), font=font(30), anchor="mm")
y += 120
d.text((W / 2, y), "MITSUBISHI ESTATE LONDON LIMITED (1)", fill=(20, 20, 20), font=font(34, True), anchor="mm")
y += 70
d.text((W / 2, y), "and", fill=(90, 90, 90), font=font(28), anchor="mm")
y += 70
d.text((W / 2, y), "CONFIDENTIAL (US LAW FIRM) (2)", fill=(20, 20, 20), font=font(34, True), anchor="mm")
y += 160
d.line((160, y, W - 160, y), fill=(120, 120, 120), width=3)
y += 70
d.text((W / 2, y), "LEASE", fill=(20, 20, 20), font=font(60, True), anchor="mm")
y += 80
d.text((W / 2, y), "of the Twelfth Floor", fill=(40, 40, 40), font=font(34), anchor="mm")
y += 60
d.text((W / 2, y), "8 Bishopsgate, London EC2N 4BQ", fill=(40, 40, 40), font=font(34), anchor="mm")
y += 100
d.line((160, y, W - 160, y), fill=(120, 120, 120), width=3)
y += 80
rows = [("Term", "10 years from 2 October 2026"), ("Net internal area", "18,400 sq ft"),
        ("Initial rent", "£72.50 per sq ft per annum"), ("Rent-free period", "24 months"),
        ("Landlord", "Mitsubishi Estate London Limited")]
for k, v in rows:
    d.text((220, y), k, fill=(70, 70, 70), font=font(28), anchor="lm")
    d.text((620, y), v, fill=(20, 20, 20), font=font(28, True), anchor="lm")
    y += 62
# a phone photo: slight tilt, soft focus, warm shadow
img = img.rotate(-1.4, resample=Image.BICUBIC, expand=False, fillcolor=(210, 205, 196))
img = img.filter(ImageFilter.GaussianBlur(0.6))
img.save(OUT, quality=82)
print(OUT)
