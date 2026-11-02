"""Build the Lintel marketing site: site/pages/*.html bodies + site/layout.html -> site/public/.

    python site/build.py

Each page starts with a front-matter block:
    <!-- title: ... | description: ... | nav: pricing -->
The output is plain static HTML (deployable to any static host); the Lintel backend also
serves it at http://127.0.0.1:8002/site/.
"""
import hashlib
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "public"
NAV = [("assistant", "Assistant", "assistant.html"), ("dashboard", "Dashboard", "dashboard.html"),
       ("pricing", "Pricing", "pricing.html"), ("about", "About", "about.html")]


def main(out=None):
    OUT = Path(out) if out else globals()["OUT"]
    layout = (HERE / "layout.html").read_text(encoding="utf-8")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(HERE / "assets", OUT / "assets")
    # cache-busting: assets/site.css -> assets/site.css?v=<hash of the file>
    for name in ("site.css", "site.js"):
        digest = hashlib.sha1((HERE / "assets" / name).read_bytes()).hexdigest()[:8]
        layout = layout.replace(f"assets/{name}", f"assets/{name}?v={digest}")
    for page in sorted((HERE / "pages").glob("*.html")):
        text = page.read_text(encoding="utf-8")
        m = re.match(r"\s*<!--(.*?)-->", text, re.S)
        meta = dict(part.split(":", 1) for part in m.group(1).split("|")) if m else {}
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        nav = "".join(f'<a href="{href}"{" aria-current=page" if meta.get("nav") == key else ""}>{label}</a>'
                      for key, label, href in NAV)
        html = (layout.replace("{{title}}", meta.get("title", "Lintel"))
                .replace("{{description}}", meta.get("description", ""))
                .replace("{{nav}}", nav)
                .replace("{{page}}", page.stem)
                .replace("{{body}}", text[m.end():] if m else text))
        (OUT / page.name).write_text(html, encoding="utf-8")
        print("built", page.name)
    return OUT


if __name__ == "__main__":
    main()
