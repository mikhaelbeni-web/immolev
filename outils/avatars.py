"""Dessine les visages d'agent proposés dans le panneau (SVG + JPG pour la photo du bot Telegram).

Usage (sur le poste de développement, Playwright requis) : python outils/avatars.py
Sortie : panneau/avatars/<id>.svg et <id>.jpg, plus panneau/avatars/liste.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SORTIE = Path(__file__).resolve().parent.parent / "panneau" / "avatars"

PEAUX = {"claire": ("#f6d3b8", "#e8b896"), "doree": ("#e6b48a", "#d29a6c"),
         "mate": ("#c98e62", "#b2774c"), "foncee": ("#8d5a3b", "#76482c")}

# id, prénom proposé, genre, peau, cheveux (style, couleur), vêtement, fond (2 couleurs), lunettes
PROFILS = [
    ("lea", "Léa", "f", "claire", ("long", "#6b4226"), "#1f3b73", ("#7dd3fc", "#6366f1"), False),
    ("ines", "Inès", "f", "doree", ("chignon", "#2b1d16"), "#0f766e", ("#99f6e4", "#0ea5e9"), True),
    ("maya", "Maya", "f", "foncee", ("boucles", "#1c1410"), "#7c2d12", ("#fde68a", "#f472b6"), False),
    ("chloe", "Chloé", "f", "claire", ("carre", "#d9a441"), "#4c1d95", ("#c4b5fd", "#22d3ee"), True),
    ("sofia", "Sofia", "f", "mate", ("long", "#2a1a12"), "#9f1239", ("#fecdd3", "#a78bfa"), False),
    ("hugo", "Hugo", "m", "claire", ("court", "#5a3a22"), "#1e3a8a", ("#93c5fd", "#14b8a6"), False),
    ("adam", "Adam", "m", "doree", ("houppe", "#1f1610"), "#111827", ("#a5b4fc", "#38bdf8"), True),
    ("noah", "Noah", "m", "foncee", ("frise", "#120c09"), "#065f46", ("#6ee7b7", "#3b82f6"), False),
    ("lucas", "Lucas", "m", "mate", ("barbe", "#3b2416"), "#334155", ("#fcd34d", "#fb7185"), True),
    ("theo", "Théo", "m", "claire", ("houppe", "#b7792f"), "#0c4a6e", ("#67e8f9", "#818cf8"), False),
]


def _cheveux_arriere(style: str, c: str) -> str:
    if style == "long":
        return f'<path fill="{c}" d="M150 250C138 118 210 98 256 98C302 98 374 118 362 250L376 430C330 452 182 452 136 430Z"/>'
    if style == "carre":
        return f'<path fill="{c}" d="M150 236C144 118 214 98 256 98C298 98 368 118 362 236L364 334C330 352 182 352 148 334Z"/>'
    if style == "chignon":
        return f'<circle cx="256" cy="98" r="44" fill="{c}"/>'
    if style == "boucles":
        bulles = [(256, 104), (210, 112), (302, 112), (174, 140), (338, 140), (158, 184), (354, 184),
                  (152, 232), (360, 232), (156, 280), (356, 280), (166, 322), (346, 322)]
        return "".join(f'<circle cx="{x}" cy="{y}" r="40" fill="{c}"/>' for x, y in bulles)
    return ""


def _cheveux_avant(style: str, c: str) -> str:
    formes = {
        "long": "M164 236C158 140 218 108 262 110C322 112 358 152 350 238C330 182 292 160 240 168C208 174 180 202 164 236Z",
        "carre": "M164 214C168 134 220 106 256 106C302 106 346 134 348 214C318 186 198 186 164 214Z",
        "chignon": "M166 232C160 140 214 112 256 112C300 112 352 140 346 232C332 172 298 150 256 150C214 150 180 172 166 232Z",
        "boucles": "M166 220C164 150 210 118 256 118C302 118 348 150 346 220C326 176 296 162 256 162C216 162 186 176 166 220Z",
        "court": "M168 222C158 138 210 108 256 108C306 108 354 138 344 222C336 180 316 158 256 156C196 158 176 180 168 222Z",
        "houppe": "M168 224C156 148 200 96 266 92C326 90 360 140 344 224C330 170 300 156 250 160C200 164 178 186 168 224Z",
        "frise": "M170 214C166 140 214 114 256 114C300 114 348 140 342 214C330 176 300 164 256 164C212 164 182 176 170 214Z",
        "barbe": "M168 222C158 138 210 108 256 108C306 108 354 138 344 222C336 180 316 158 256 156C196 158 176 180 168 222Z",
    }
    s = f'<path fill="{c}" d="{formes[style]}"/>'
    if style == "frise":
        s += "".join(f'<circle cx="{x}" cy="{y}" r="16" fill="{c}"/>'
                     for x, y in [(188, 150), (216, 128), (248, 120), (280, 122), (310, 132), (332, 154), (200, 176), (320, 176)])
    if style == "barbe":
        s += (f'<path fill="{c}" d="M174 252C176 334 214 352 256 352C298 352 336 334 338 252'
              f'C326 296 302 310 256 312C210 310 186 296 174 252Z"/>')
    return s


def svg(p) -> str:
    _id, _nom, genre, peau, (style, ch), habit, (f1, f2), lunettes = p
    clair, ombre = PEAUX[peau]
    levres = "#c0605a" if genre == "f" else ombre
    cils = ('<path d="M206 238l-8-5M300 238l8-5" stroke="#1f2937" stroke-width="3" stroke-linecap="round"/>'
            if genre == "f" else "")
    verres = ('<g fill="#ffffff22" stroke="#111827" stroke-width="5"><rect x="190" y="222" width="62" height="48" rx="18"/>'
              '<rect x="260" y="222" width="62" height="48" rx="18"/></g>'
              '<path d="M252 242q4-5 8 0" stroke="#111827" stroke-width="5" fill="none"/>' if lunettes else "")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<defs>
<linearGradient id="fond" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{f1}"/><stop offset="1" stop-color="{f2}"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".42" r=".5"><stop offset="0" stop-color="#ffffff" stop-opacity=".55"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
<linearGradient id="habit" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{habit}"/><stop offset="1" stop-color="#0b1020"/></linearGradient>
</defs>
<rect width="512" height="512" fill="url(#fond)"/>
<circle cx="256" cy="220" r="230" fill="url(#halo)"/>
<g stroke="#ffffff" stroke-opacity=".25" stroke-width="2" fill="none">
<path d="M40 120h60l20 20h40M472 380h-60l-20-20h-40M60 420h50M430 90h-40"/>
</g>
<g fill="#ffffff" fill-opacity=".6"><circle cx="160" cy="140" r="4"/><circle cx="350" cy="360" r="4"/><circle cx="110" cy="420" r="4"/><circle cx="390" cy="90" r="4"/></g>
{_cheveux_arriere(style, ch)}
<path fill="url(#habit)" d="M90 512C104 404 176 372 256 372C336 372 408 404 422 512Z"/>
<path fill="#ffffff" fill-opacity=".9" d="M226 376L256 420L286 376Z"/>
<rect x="226" y="300" width="60" height="86" rx="24" fill="{ombre}"/>
<ellipse cx="170" cy="250" rx="15" ry="24" fill="{ombre}"/><ellipse cx="342" cy="250" rx="15" ry="24" fill="{ombre}"/>
<ellipse cx="256" cy="238" rx="88" ry="104" fill="{clair}"/>
{_cheveux_avant(style, ch)}
<path d="M200 212q22-12 42-2M270 210q20-10 42 2" stroke="{ch}" stroke-width="7" stroke-linecap="round" fill="none"/>
<ellipse cx="222" cy="248" rx="10" ry="12" fill="#1f2937"/><ellipse cx="290" cy="248" rx="10" ry="12" fill="#1f2937"/>
<circle cx="226" cy="243" r="4" fill="#ffffff"/><circle cx="294" cy="243" r="4" fill="#ffffff"/>
{cils}
<path d="M256 258q-8 26 0 30q6 2 10-2" stroke="{ombre}" stroke-width="5" stroke-linecap="round" fill="none"/>
<ellipse cx="204" cy="284" rx="16" ry="9" fill="#f43f5e" fill-opacity=".14"/><ellipse cx="308" cy="284" rx="16" ry="9" fill="#f43f5e" fill-opacity=".14"/>
<path d="M232 306q24 20 48 0" stroke="{levres}" stroke-width="7" stroke-linecap="round" fill="none"/>
{verres}
<g><rect x="330" y="236" width="22" height="34" rx="10" fill="#0f172a"/><circle cx="341" cy="253" r="6" fill="#22d3ee"/>
<circle cx="341" cy="253" r="14" fill="#22d3ee" fill-opacity=".25"/>
<path d="M341 270q0 40-58 52" stroke="#0f172a" stroke-width="4" fill="none" stroke-linecap="round"/><circle cx="283" cy="322" r="5" fill="#0f172a"/></g>
</svg>'''


def main() -> None:
    from playwright.sync_api import sync_playwright
    SORTIE.mkdir(parents=True, exist_ok=True)
    liste = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        page = nav.new_page(viewport={"width": 512, "height": 512})
        for p in PROFILS:
            code = svg(p)
            (SORTIE / f"{p[0]}.svg").write_text(code, encoding="utf-8")
            page.set_content(f'<html><body style="margin:0">{code}</body></html>')
            page.screenshot(path=str(SORTIE / f"{p[0]}.jpg"), type="jpeg", quality=90)
            liste.append({"id": p[0], "nom": p[1], "genre": p[2]})
        nav.close()
    (SORTIE / "liste.json").write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(liste)} visages dans {SORTIE}")


if __name__ == "__main__":
    main()
