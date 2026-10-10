# ruff: noqa: E501  (SVG literals read better unbroken; this is a drawing script)
"""Compose the README's hero image — one JSON spec in, a backend's layers out.

Not shipped code. Writes docs/hero.svg, then rasterises it to docs/hero.png with a
headless Chromium (the README shows the PNG: GitHub's `<img>` view of an SVG loads
no fonts). Needs the Inter and DejaVu Sans Mono fonts and Pillow (to crop).

Same drafting-sheet family as the author's other repos. The spec excerpt follows
examples/user-auth-project/models/users.model.json; no version or counts on it.

Usage, from the repository root:

    make hero
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT_SVG = ROOT / "docs" / "hero.svg"
OUT_PNG = ROOT / "docs" / "hero.png"

#: The GitHub social-preview size, which the README shows scaled to its column.
W, H = 1280, 640

GROUND = "#111219"
GRID = "#1a1c26"
INK = "#eceefb"
SOFT = "#e1e3ef"
DIM = "#b3b7cf"
FRAME = "#4a4e66"
PANEL = "#1a1c28"
VIOLET = "#b9a6ff"
LIME = "#c4f06b"
SANS = "Inter, 'DejaVu Sans', sans-serif"
DISPLAY = "'Inter Display', Inter, sans-serif"
MONO = "'DejaVu Sans Mono', monospace"


def text(
    x: float,
    y: float,
    s: str,
    *,
    size: float,
    fill: str = INK,
    family: str = SANS,
    weight: int = 400,
    anchor: str = "start",
    spacing: float = 0,
    italic: bool = False,
) -> str:
    style = ' font-style="italic"' if italic else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'letter-spacing="{spacing}"{style} xml:space="preserve">{escape(s)}</text>'
    )


def sheet() -> list[str]:
    """Grid, border with zone marks, registration marks — the family's drafting sheet."""
    out = [f'<rect width="{W}" height="{H}" fill="{GROUND}"/>']
    for gx in range(0, W, 20):
        width = 0.9 if gx % 100 == 0 else 0.4
        out.append(
            f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="{GRID}" stroke-width="{width}"/>'
        )
    for gy in range(0, H, 20):
        width = 0.9 if gy % 100 == 0 else 0.4
        out.append(
            f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="{GRID}" stroke-width="{width}"/>'
        )
    out.append(
        f'<rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" stroke="{GRID}"/>'
    )
    out.append(
        f'<rect x="30" y="30" width="{W - 60}" height="{H - 60}" fill="none" '
        f'stroke="{FRAME}" stroke-width="1.5"/>'
    )
    zw = (W - 60) / 8
    for i in range(8):
        x = 30 + zw * i
        if i:
            out.append(f'<line x1="{x}" y1="16" x2="{x}" y2="30" stroke="{FRAME}"/>')
            out.append(
                f'<line x1="{x}" y1="{H - 30}" x2="{x}" y2="{H - 16}" stroke="{FRAME}"/>'
            )
        for ty in (27, H - 19):
            out.append(
                text(
                    x + zw / 2,
                    ty,
                    str(8 - i),
                    size=9,
                    fill=DIM,
                    family=MONO,
                    anchor="middle",
                )
            )
    zh = (H - 60) / 4
    for i in range(4):
        y = 30 + zh * i
        if i:
            out.append(f'<line x1="16" y1="{y}" x2="30" y2="{y}" stroke="{FRAME}"/>')
            out.append(
                f'<line x1="{W - 30}" y1="{y}" x2="{W - 16}" y2="{y}" stroke="{FRAME}"/>'
            )
        for x in (23, W - 23):
            out.append(
                text(
                    x,
                    y + zh / 2 + 3,
                    "ABCD"[i],
                    size=9,
                    fill=DIM,
                    family=MONO,
                    anchor="middle",
                )
            )
    for cx, cy in ((48, 48), (48, H - 48)):
        out += [
            f'<circle cx="{cx}" cy="{cy}" r="7" fill="none" stroke="{VIOLET}"/>',
            f'<line x1="{cx - 11}" y1="{cy}" x2="{cx + 11}" y2="{cy}" stroke="{VIOLET}"/>',
            f'<line x1="{cx}" y1="{cy - 11}" x2="{cx}" y2="{cy + 11}" stroke="{VIOLET}"/>',
        ]
    return out


LOGO_SVG = ROOT / "docs" / "logo.svg"
#: Logo tile: size and top-left, set so it spans the wordmark's x-height to descender.
LOGO_SIZE, LOGO_X, LOGO_Y = 88, 64, 50
#: Wordmark and subtitles start right of the logo.
TEXT_X = LOGO_X + LOGO_SIZE + 20


def logo() -> str:
    """The approved logo, nested inline so the hero stays a single file."""
    inner = LOGO_SVG.read_text().strip()
    inner = inner.replace(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">', "", 1
    ).removesuffix("</svg>")
    return (
        f'<svg x="{LOGO_X}" y="{LOGO_Y}" width="{LOGO_SIZE}" height="{LOGO_SIZE}" '
        f'viewBox="0 0 64 64">{inner}</svg>'
    )


def wordmark() -> list[str]:
    return [
        logo(),
        f'<text x="{TEXT_X}" y="122" font-family="{DISPLAY}" font-size="72" font-weight="800" '
        f'letter-spacing="-2"><tspan fill="{INK}">model</tspan>'
        f'<tspan fill="{VIOLET}">-generator</tspan></text>',
        text(
            TEXT_X + 4,
            170,
            "JSON specs in, a production-ready API backend out.",
            size=25,
            fill=SOFT,
        ),
        text(
            TEXT_X + 4,
            198,
            "One-shot scaffolding: database models, API schemas, routes, tests and "
            "migrations.",
            size=15,
            fill=DIM,
        ),
    ]


def title_block() -> list[str]:
    x, y, w, h = 842, 62, 376, 64
    half = w / 2 - 6
    cells = [(0.0, "ON PYPI", "model-generator-kit"), (half, "STACK", "python-fastapi")]
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{GROUND}" stroke="{FRAME}" '
        f'stroke-width="1.2"/>',
        f'<line x1="{x}" y1="{y + h / 2 + 4}" x2="{x + w}" y2="{y + h / 2 + 4}" stroke="{FRAME}"/>',
        f'<line x1="{x + half}" y1="{y + h / 2 + 4}" x2="{x + half}" y2="{y + h}" '
        f'stroke="{FRAME}"/>',
        text(x + 10, y + 14, "PROJECT", size=8, fill=DIM, family=MONO, spacing=1.5),
        text(x + 10, y + 30, "model-generator", size=14, weight=700, family=MONO),
    ]
    for cx, label, value in cells:
        out.append(
            text(x + cx + 10, y + 47, label, size=8, fill=DIM, family=MONO, spacing=1.5)
        )
        out.append(
            text(
                x + cx + 10,
                y + 61,
                value,
                size=11,
                family=MONO,
                fill=VIOLET if cx else INK,
            )
        )
    return out


def caption(x: float, y: float, s: str, colour: str = VIOLET) -> str:
    return text(x, y, s, size=10, fill=colour, family=MONO, spacing=2, weight=700)


#: (indent, key, value) — a users.model.json excerpt.
SPEC = [
    (0, "", "{"),
    (1, "domain", '"users",'),
    (1, "entities", "{"),
    (2, "User", "{"),
    (3, "table", '"users",'),
    (3, "fields", "{"),
    (4, "email", "{"),
    (5, "type", '"text",'),
    (5, "max_length", "255,"),
    (5, "unique", "true"),
]


def spec() -> list[str]:
    x, y, w, h = 64, 254, 360, 270
    out = [
        caption(x, y - 12, "THE SPEC"),
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{PANEL}" stroke="{FRAME}"/>',
        f'<line x1="{x}" y1="{y + 28}" x2="{x + w}" y2="{y + 28}" stroke="{FRAME}"/>',
        text(
            x + 14, y + 19, "models/users.model.json", size=11.5, family=MONO, fill=SOFT
        ),
    ]
    for i, (indent, key, value) in enumerate(SPEC):
        ty = y + 52 + i * 21
        tx = x + 16 + indent * 16
        if key:
            out.append(
                f'<text x="{tx}" y="{ty}" font-family="{MONO}" font-size="12.5" '
                f'xml:space="preserve"><tspan fill="{VIOLET}">"{escape(key)}"</tspan>'
                f'<tspan fill="{SOFT}">: </tspan><tspan fill="{LIME}">{escape(value)}</tspan></text>'
            )
        else:
            out.append(text(tx, ty, value, size=12.5, family=MONO, fill=SOFT))
    return out


#: What one run writes: (path, what it holds).
OUTPUTS = [
    ("database/models/", "SQLAlchemy ORM · constraints, indexes"),
    ("api/models/", "Pydantic schemas · validators"),
    ("api/routes/", "FastAPI CRUD endpoints"),
    ("tests/contract/", "pytest contract tests · FactoryBoy"),
    ("alembic/", "migrations"),
]


def outputs() -> list[str]:
    x, y, w, h, gap = 812, 254, 406, 46, 10
    hub_x, hub_y = 652, 389
    out = [caption(x, y - 12, "ONE RUN WRITES")]
    for i, (path, what) in enumerate(OUTPUTS):
        cy = y + i * (h + gap)
        mid = cy + h / 2
        out += [
            f'<path d="M{hub_x + 70},{hub_y} C{hub_x + 120},{hub_y} {x - 50},{mid} {x - 4},{mid}" '
            f'fill="none" stroke="{VIOLET}" stroke-width="1.3" opacity="0.7"/>',
            f'<rect x="{x}" y="{cy}" width="{w}" height="{h}" rx="5" fill="{PANEL}" '
            f'stroke="{FRAME}"/>',
            f'<rect x="{x}" y="{cy}" width="4" height="{h}" rx="2" fill="{LIME}"/>',
            text(x + 16, cy + 19, path, size=12.5, weight=700, family=MONO, fill=INK),
            text(x + 16, cy + 37, what, size=12, fill=DIM),
        ]
    return out


def command() -> list[str]:
    """The middle: the one command, between the spec and what it writes."""
    cx, cy = 618, 389
    return [
        f'<line x1="430" y1="{cy}" x2="{cx - 120}" y2="{cy}" stroke="{VIOLET}" '
        f'stroke-width="1.6" stroke-dasharray="5 3"/>',
        f'<rect x="{cx - 114}" y="{cy - 22}" width="218" height="44" rx="22" fill="{VIOLET}"/>',
        text(
            cx - 5,
            cy + 5,
            "model-gen --target all",
            size=13,
            weight=700,
            family=MONO,
            fill=GROUND,
            anchor="middle",
        ),
        text(
            cx - 5,
            cy + 46,
            "one shot, no runtime dependency",
            size=11.5,
            fill=DIM,
            anchor="middle",
        ),
        text(
            cx - 5,
            cy - 34,
            "model-val checks the spec first",
            size=11.5,
            fill=DIM,
            anchor="middle",
        ),
    ]


def strip() -> list[str]:
    items = [
        ("contract-tested", "the generated suite passes"),
        ("stack-agnostic", "one generator, pluggable stacks"),
        ("yours to extend", "business logic stays in your code"),
    ]
    x0, y, w, h, gap = 64, 552, 376, 40, 9
    out = []
    for i, (name, sub) in enumerate(items):
        x = x0 + i * (w + gap)
        out += [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{PANEL}" '
            f'stroke="{FRAME}" stroke-width="0.8"/>',
            f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{VIOLET}"/>',
            text(x + 16, y + 25, name, size=12.5, weight=700, family=MONO, fill=VIOLET),
            text(x + 16 + len(name) * 7.6 + 10, y + 25, sub, size=12, fill=SOFT),
        ]
    return out


def svg() -> str:
    parts = (
        sheet() + wordmark() + title_block() + spec() + outputs() + command() + strip()
    )
    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">\n  {body}\n</svg>\n'
    )


def chromium() -> str:
    for candidate in (
        os.environ.get("CHROMIUM"),
        "/opt/pw-browsers/chromium",
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit("hero: no Chromium found; set CHROMIUM=/path/to/chrome")


def main() -> None:
    OUT_SVG.write_text(svg())
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "hero.html"
        page.write_text(
            f'<html><body style="margin:0;overflow:hidden">{svg()}</body></html>'
        )
        subprocess.run(
            [
                chromium(),
                "--headless=new",
                "--no-sandbox",
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                f"--window-size={W},{H + 200}",
                f"--screenshot={OUT_PNG}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    # Headless Chromium's viewport is shorter than its window: shoot tall, then crop.
    from PIL import Image  # type: ignore[import-not-found, unused-ignore]

    with Image.open(OUT_PNG) as shot:
        shot.crop((0, 0, W * 2, H * 2)).save(OUT_PNG, optimize=True)
    print(f"wrote {OUT_SVG.relative_to(ROOT)} and {OUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
