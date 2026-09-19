from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "web" / "standalone"
DIST = ROOT / "apps" / "web" / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.2.0"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)

    css_name = f"app.{digest(SOURCE / 'app.css')}.css"
    js_name = f"app.{digest(SOURCE / 'app.js')}.js"
    shutil.copy2(SOURCE / "app.css", DIST / "assets" / css_name)
    js_source = (SOURCE / "app.js").read_text(encoding="utf-8")
    build_stamp = digest(SOURCE / "app.js")[:7]
    js_source = js_source.replace("const BUILD = 'dev'", f"const BUILD = '{build_stamp}'", 1)
    (DIST / "assets" / js_name).write_text(js_source, encoding="utf-8")

    index = (SOURCE / "index.html").read_text(encoding="utf-8")
    index = index.replace("/assets/app.css", f"/assets/{css_name}")
    index = index.replace("/assets/app.js", f"/assets/{js_name}")
    (DIST / "index.html").write_text(index, encoding="utf-8")

    for name in ("icon.svg", "icon-192.png", "icon-512.png", "manifest.webmanifest"):
        shutil.copy2(SOURCE / name, DIST / name)

    shell = [
        "/", "/index.html", "/manifest.webmanifest", "/icon.svg", "/icon-192.png",
        "/icon-512.png", f"/assets/{css_name}", f"/assets/{js_name}",
    ]
    source_sw = (SOURCE / "sw.js").read_text(encoding="utf-8")
    cache_id = hashlib.sha256("\n".join(shell).encode()).hexdigest()[:12]
    source_sw = source_sw.replace("const CACHE = 'hermes-companion-v1'", f"const CACHE = 'hermes-companion-{VERSION}-{cache_id}'")
    start = source_sw.index("const SHELL =")
    end = source_sw.index("\n\nself.addEventListener", start)
    source_sw = source_sw[:start] + f"const SHELL = {json.dumps(shell)}" + source_sw[end:]
    (DIST / "sw.js").write_text(source_sw, encoding="utf-8")

    manifest = json.loads((DIST / "manifest.webmanifest").read_text(encoding="utf-8"))
    manifest["id"] = "/"
    manifest["categories"] = ["productivity", "utilities"]
    manifest["version"] = VERSION
    (DIST / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    files = sorted(path.relative_to(DIST).as_posix() for path in DIST.rglob("*") if path.is_file())
    print(f"Built Hermes Companion web {VERSION}: {len(files)} files")
    for file in files:
        print(file)


if __name__ == "__main__":
    main()
