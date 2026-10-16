"""Dessine les visages d'agent proposés dans le panneau (SVG + JPG pour la photo du bot Telegram).

Style « personnage 3D » : grosse tête, grands yeux brillants, volumes en dégradés et ombres douces.
Usage (poste de développement, Playwright requis) : CHROMIUM=<chemin> python outils/avatars.py
Sortie : panneau/avatars/<id>.svg et <id>.jpg, plus panneau/avatars/liste.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SORTIE = Path(__file__).resolve().parent.parent / "panneau" / "avatars"

# clair, moyen, ombre
PEAUX = {"claire": ("#ffe3cf", "#f5c4a1", "#d99670"), "doree": ("#f6cfa6", "#e3a877", "#b9784c"),
         "mate": ("#e2ad80", "#c98a5b", "#9a5f37"), "foncee": ("#a8704a", "#8a5634", "#5e3620")}

# id, prénom, genre, peau, (coiffure, couleur), haut, fond, yeux, lunettes (couleur de monture ou None)
PROFILS = [
    ("lea", "Léa", "f", "claire", ("long", "#7a4a2a"), "#ffffff", "#ffd6e0", "#3b82f6", None),
    ("ines", "Inès", "f", "doree", ("chignon", "#3a2418"), "#1e3a5f", "#c7f0e8", "#5b3a1e", "#c2410c"),
    ("maya", "Maya", "f", "foncee", ("boucles", "#231710"), "#f59e0b", "#e9d5ff", "#4a2a14", None),
    ("chloe", "Chloé", "f", "claire", ("carre", "#e0b04f"), "#7c3aed", "#cfe8ff", "#16a34a", "#1f2937"),
    ("sofia", "Sofia", "f", "mate", ("long", "#2c1a10"), "#e11d48", "#fff1c2", "#5b3a1e", None),
    ("hugo", "Hugo", "m", "claire", ("court", "#6b4428"), "#2563eb", "#ffe4c7", "#2f80d1", None),
    ("adam", "Adam", "m", "doree", ("houppe", "#22170f"), "#ffffff", "#dbeafe", "#4a2a14", "#111827"),
    ("noah", "Noah", "m", "foncee", ("frise", "#140d08"), "#0f766e", "#fde2c4", "#3b2312", None),
    ("lucas", "Lucas", "m", "mate", ("barbe", "#3f2617"), "#334155", "#d1fae5", "#5b3a1e", "#7c2d12"),
    ("theo", "Théo", "m", "claire", ("houppe", "#c98a3c"), "#16a34a", "#e0e7ff", "#3a8a5c", None),
]

# Les coiffures sont dessinées pour une tête (256,238) rx88 ry104, puis agrandies vers la tête 3D.
AGRANDIR = 'transform="translate(256 232) scale(1.36 1.24) translate(-256 -238)"'


def _cheveux_arriere(style: str) -> str:
    if style == "long":
        return '<path d="M150 250C138 118 210 98 256 98C302 98 374 118 362 250L372 400C330 420 182 420 140 400Z"/>'
    if style == "carre":
        return '<path d="M150 236C144 118 214 98 256 98C298 98 368 118 362 236L362 318C330 336 182 336 150 318Z"/>'
    if style == "chignon":
        return '<circle cx="256" cy="92" r="42"/>'
    if style == "boucles":
        bulles = [(256, 104), (210, 110), (302, 110), (172, 138), (340, 138), (156, 182), (356, 182),
                  (150, 228), (362, 228), (154, 272), (358, 272), (166, 308), (346, 308)]
        return "".join(f'<circle cx="{x}" cy="{y}" r="38"/>' for x, y in bulles)
    return ""


def _cheveux_avant(style: str) -> str:
    formes = {
        "long": "M162 240C154 138 218 104 262 106C324 108 362 150 352 242C334 178 294 156 240 164C206 170 178 200 162 240Z",
        "carre": "M162 218C166 130 220 102 256 102C304 102 348 130 350 218C320 184 196 184 162 218Z",
        "chignon": "M164 232C158 138 214 108 256 108C302 108 354 138 348 232C334 168 298 146 256 146C214 146 178 168 164 232Z",
        "boucles": "M164 222C162 148 210 114 256 114C302 114 350 148 348 222C326 172 296 158 256 158C216 158 186 172 164 222Z",
        "court": "M166 226C154 134 210 102 256 102C308 102 358 134 346 226C338 178 316 154 256 152C196 154 174 178 166 226Z",
        "houppe": "M166 228C152 146 198 88 268 84C330 82 364 136 346 228C330 166 300 152 250 156C198 160 176 184 166 228Z",
        "frise": "M168 218C164 136 214 108 256 108C300 108 350 136 344 218C330 172 300 160 256 160C212 160 182 172 168 218Z",
        "barbe": "M166 226C154 134 210 102 256 102C308 102 358 134 346 226C338 178 316 154 256 152C196 154 174 178 166 226Z",
    }
    s = f'<path d="{formes[style]}"/>'
    if style in ("boucles", "frise"):
        s += "".join(f'<circle cx="{x}" cy="{y}" r="15"/>'
                     for x, y in [(186, 148), (214, 124), (248, 116), (282, 118), (312, 128), (334, 152), (198, 176), (322, 176)])
    return s


def _reflet(style: str) -> str:
    """Mèche de lumière sur le dessus des cheveux (volume)."""
    if style in ("boucles", "frise"):
        return '<ellipse cx="236" cy="122" rx="40" ry="12" transform="rotate(-12 236 122)"/>'
    return '<path d="M200 138C222 118 258 112 292 118C262 122 232 130 206 150Z"/>'


def svg(p) -> str:
    ident, _nom, genre, peau, (style, ch), haut, fond, yeux, lunettes = p
    clair, moyen, ombre = PEAUX[peau]
    f = genre == "f"
    cils = ('<path d="M174 236q-10-6-14-14M180 228q-8-8-10-16M338 236q10-6 14-14M332 228q8-8 10-16" '
            'stroke="#1b1210" stroke-width="5" stroke-linecap="round" fill="none"/>') if f else ""
    monture = ""
    if lunettes:
        monture = (f'<g fill="#ffffff" fill-opacity=".12" stroke="{lunettes}" stroke-width="9" stroke-linejoin="round">'
                   '<rect x="150" y="212" width="94" height="76" rx="30"/><rect x="268" y="212" width="94" height="76" rx="30"/></g>'
                   f'<path d="M244 240q12-12 24 0" stroke="{lunettes}" stroke-width="8" fill="none"/>'
                   '<path d="M164 222l20-6M282 222l20-6" stroke="#ffffff" stroke-opacity=".7" stroke-width="5" stroke-linecap="round"/>')
    barbe = ""
    if style == "barbe":
        barbe = (f'<path fill="{ch}" d="M148 262C150 352 200 372 256 372C312 372 362 352 364 262'
                 'C346 318 316 336 256 338C196 336 166 318 148 262Z"/>'
                 f'<path fill="{ch}" d="M210 316q46-18 92 0q-10 10-46 8q-36 2-46-8Z"/>')
    levres = "#c2414b" if f else "#9b3b3b"
    oeil = lambda cx: (  # noqa: E731
        f'<ellipse cx="{cx}" cy="250" rx="27" ry="31" fill="#ffffff"/>'
        f'<circle cx="{cx + 2}" cy="254" r="21" fill="url(#iris)"/>'
        f'<circle cx="{cx + 2}" cy="254" r="10" fill="#0b0b0f"/>'
        f'<circle cx="{cx + 10}" cy="244" r="7" fill="#ffffff"/><circle cx="{cx - 6}" cy="264" r="3.5" fill="#ffffff" fill-opacity=".8"/>'
        f'<path d="M{cx - 30} 242q30-30 60 0" stroke="#1b1210" stroke-width="{7 if f else 5}" fill="none" stroke-linecap="round"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
<defs>
<radialGradient id="fond" cx=".5" cy=".38" r=".75"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="{fond}"/><stop offset="1" stop-color="{fond}" stop-opacity=".85"/></radialGradient>
<radialGradient id="peau" cx=".38" cy=".32" r=".8"><stop offset="0" stop-color="{clair}"/><stop offset=".6" stop-color="{moyen}"/><stop offset="1" stop-color="{ombre}"/></radialGradient>
<radialGradient id="iris" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#ffffff" stop-opacity=".5"/><stop offset=".25" stop-color="{yeux}"/><stop offset="1" stop-color="#0d0d14"/></radialGradient>
<linearGradient id="cheveux" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ch}" stop-opacity=".82"/><stop offset=".35" stop-color="{ch}"/><stop offset="1" stop-color="#000000" stop-opacity=".9"/></linearGradient>
<linearGradient id="haut" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{haut}"/><stop offset="1" stop-color="{haut}" stop-opacity=".75"/></linearGradient>
<filter id="flou" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="9"/></filter>
<filter id="flou2" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
<filter id="portee" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000000" flood-opacity=".22"/></filter>
<clipPath id="tete"><ellipse cx="256" cy="232" rx="120" ry="128"/></clipPath>
</defs>
<rect width="512" height="512" fill="{fond}"/>
<rect width="512" height="512" fill="url(#fond)"/>
<g filter="url(#portee)">
<g fill="url(#cheveux)" {AGRANDIR}>{_cheveux_arriere(style)}</g>
<path fill="url(#haut)" d="M96 512C100 430 160 392 256 392C352 392 412 430 416 512Z"/>
<path fill="#000000" fill-opacity=".12" d="M150 512C160 470 190 440 230 430L256 470L282 430C322 440 352 470 362 512Z"/>
<path fill="{moyen}" d="M214 340h84v52q-42 40-84 0Z"/>
<path fill="{ombre}" fill-opacity=".55" d="M214 352q42 26 84 0v-12h-84Z" filter="url(#flou2)"/>
<path fill="#ffffff" fill-opacity="{'.95' if haut != '#ffffff' else '.0'}" d="M206 392l50 46l50-46l-14-8l-36 30l-36-30Z"/>
<ellipse cx="136" cy="250" rx="20" ry="30" fill="{moyen}"/><ellipse cx="376" cy="250" rx="20" ry="30" fill="{moyen}"/>
<ellipse cx="256" cy="232" rx="120" ry="128" fill="url(#peau)"/>
</g>
<g clip-path="url(#tete)">
<ellipse cx="256" cy="372" rx="130" ry="40" fill="{ombre}" fill-opacity=".45" filter="url(#flou)"/>
<ellipse cx="224" cy="168" rx="70" ry="40" fill="#ffffff" fill-opacity=".28" filter="url(#flou)"/>
<g fill="{ombre}" fill-opacity=".45" filter="url(#flou)" {AGRANDIR}>{_cheveux_avant(style)}</g>
</g>
<ellipse cx="180" cy="296" rx="26" ry="15" fill="#ff6b81" fill-opacity=".35" filter="url(#flou2)"/>
<ellipse cx="332" cy="296" rx="26" ry="15" fill="#ff6b81" fill-opacity=".35" filter="url(#flou2)"/>
{oeil(194)}{oeil(318)}
{cils}
<path d="M164 {204 if f else 202}q30-{16 if f else 12} 60-2M288 {202 if f else 200}q30-{14 if f else 10} 60 {4 if f else 2}" stroke="{ch}" stroke-width="{8 if f else 11}" stroke-linecap="round" fill="none"/>
<ellipse cx="256" cy="292" rx="16" ry="12" fill="{ombre}" fill-opacity=".55" filter="url(#flou2)"/>
<ellipse cx="252" cy="286" rx="7" ry="5" fill="#ffffff" fill-opacity=".55"/>
{barbe}
<path d="M218 318q38 34 76 0q-2 6-6 12q-32 26-64 0q-4-6-6-12Z" fill="#5a1620"/>
<path d="M224 320q32 10 64 0l-3 8q-29 8-58 0Z" fill="#ffffff"/>
<path d="M234 336q22 12 44 0q-22-8-44 0Z" fill="#e0525f"/>
<path d="M214 316q42 40 84 0" stroke="{levres}" stroke-width="4" fill="none" stroke-linecap="round"/>
<g fill="url(#cheveux)" {AGRANDIR}>{_cheveux_avant(style)}</g>
<g fill="#ffffff" fill-opacity=".28" filter="url(#flou2)" {AGRANDIR}>{_reflet(style)}</g>
{monture}
</svg>'''


def main() -> None:
    from playwright.sync_api import sync_playwright
    SORTIE.mkdir(parents=True, exist_ok=True)
    for vieux in SORTIE.glob("*.*"):
        vieux.unlink()
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
