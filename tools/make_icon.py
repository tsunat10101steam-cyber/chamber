"""static/icon.svg → static/icon-512.png, static/icon-192.png, app.ico

Chromium(Playwright) 또는 Edge/Chrome headless 로 SVG 를 투명 배경 PNG 로 그린 뒤 Pillow 로 ICO 를 만든다.
아이콘을 고쳤을 때만 다시 실행하면 된다:  python tools/make_icon.py
이미 그려 둔 1024px PNG 가 있으면:            python tools/make_icon.py --png 그림.png
"""
import os
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "static" / "icon.svg"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def render(svg=SVG, size=1024):
    html = (f'<html><body style="margin:0;background:transparent">'
            f'<img src="{svg.as_uri()}" width="{size}" height="{size}"></body></html>')
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": size, "height": size})
            page.set_content(html)
            page.wait_for_timeout(200)
            png = page.screenshot(omit_background=True)
            b.close()
        return Image.open(BytesIO(png)).convert("RGBA")
    except ImportError:
        pass
    exe = next(b for b in BROWSERS if os.path.exists(b))
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "i.html"
        page.write_text(html, encoding="utf-8")
        out = Path(tmp) / "o.png"
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=00000000", f"--window-size={size},{size}",
                        f"--user-data-dir={tmp}\\ud", f"--screenshot={out}", page.as_uri()],
                       check=True, timeout=60, capture_output=True)
        return Image.open(out).convert("RGBA").copy()


def main():
    img = Image.open(sys.argv[2]).convert("RGBA") if sys.argv[1:2] == ["--png"] else render()
    img.resize((512, 512), Image.LANCZOS).save(ROOT / "static" / "icon-512.png")
    img.resize((192, 192), Image.LANCZOS).save(ROOT / "static" / "icon-192.png")
    img.save(ROOT / "app.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("ok")


if __name__ == "__main__":
    main()
