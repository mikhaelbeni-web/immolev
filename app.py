"""Interface de relecture : photo -> extraction -> l'opticien corrige et valide -> envoi direct au logiciel principal.

Lancer : uvicorn app:app --port 8000  puis ouvrir http://localhost:8000
"""
from __future__ import annotations

import html
from typing import Callable

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from ordonnance.destination import Destination, LogicielNonConfigure, tracer
from ordonnance.extract import extraire
from ordonnance.schema import Ordonnance
from ordonnance.validation import valider

app = FastAPI(title="Optizien, saisie d'ordonnance")
app.state.extracteur: Callable[[bytes, str], Ordonnance] = extraire
app.state.destination: Destination = LogicielNonConfigure()

PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Saisie ordonnance</title>
<style>body{{font-family:system-ui;max-width:760px;margin:24px auto;padding:0 16px}}label{{display:block;margin:6px 0}}
input,textarea{{font:inherit;width:100%;box-sizing:border-box}}.bloquant{{color:#b00020}}.a_verifier{{color:#a15c00}}
button{{font:inherit;padding:8px 16px;margin-top:12px}}</style><body>{corps}</body></html>"""


@app.get("/", response_class=HTMLResponse)
def accueil() -> str:
    return PAGE.format(corps="""<h1>Nouvelle ordonnance</h1>
<form action="/extraire" method="post" enctype="multipart/form-data">
<input type="file" name="photo" accept="image/*" capture="environment" required><button>Lire l'ordonnance</button></form>""")


def _formulaire(ordo: Ordonnance) -> str:
    alertes = valider(ordo)
    lignes = "".join(f'<li class="{a.niveau}"><b>{a.champ}</b> : {html.escape(a.message)}</li>' for a in alertes) or "<li>Aucune alerte</li>"
    donnees = html.escape(ordo.model_dump_json(indent=2))
    return PAGE.format(corps=f"""<h1>Relecture</h1><p>Vérifie chaque valeur contre la photo. Rien n'est envoyé tant que tu ne valides pas.</p>
<ul>{lignes}</ul>
<form action="/valider" method="post"><label>Données extraites (modifiables)
<textarea name="donnees" rows="40">{donnees}</textarea></label><button>Valider</button></form>""")


@app.post("/extraire", response_class=HTMLResponse)
async def extraire_photo(photo: UploadFile = File(...)) -> str:
    ordo = app.state.extracteur(await photo.read(), photo.content_type or "image/jpeg")
    return _formulaire(ordo)


@app.post("/valider", response_class=HTMLResponse)
def valider_saisie(donnees: str = Form(...)) -> str:
    ordo = Ordonnance.model_validate_json(donnees)
    alertes = valider(ordo)
    if any(a.niveau == "bloquant" for a in alertes):
        return _formulaire(ordo)
    try:
        reference = app.state.destination.envoyer(ordo)
    except Exception as erreur:
        tracer("envoi_ordonnance", "-", f"echec: {type(erreur).__name__}")
        return PAGE.format(corps=f"<h1>Non envoyée</h1><p>{html.escape(str(erreur))}</p><a href='/'>Retour</a>")
    tracer("envoi_ordonnance", reference, "ok")
    return PAGE.format(corps=f"<h1>Ordonnance envoyée au logiciel</h1><p>Référence : {html.escape(reference)}</p><a href='/'>Suivante</a>")
