"""Interface de relecture : photo d'un document -> extraction -> le gestionnaire corrige et valide -> envoi au logiciel de comptabilité.

Lancer : uvicorn app:app --port 8000  puis ouvrir http://localhost:8000
"""
from __future__ import annotations

import html
from typing import Callable

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from document.destination import Destination, LogicielNonConfigure, tracer
from document.extract import extraire
from document.schema import Document
from document.validation import valider

app = FastAPI(title="Immolev, lecture de documents")
app.state.extracteur: Callable[[bytes, str], Document] = extraire
app.state.destination: Destination = LogicielNonConfigure()

PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Lecture de document</title>
<style>body{{font-family:system-ui;max-width:760px;margin:24px auto;padding:0 16px}}label{{display:block;margin:6px 0}}
input,textarea{{font:inherit;width:100%;box-sizing:border-box}}.bloquant{{color:#b00020}}.a_verifier{{color:#a15c00}}
button{{font:inherit;padding:8px 16px;margin-top:12px}}</style><body>{corps}</body></html>"""


@app.get("/", response_class=HTMLResponse)
def accueil() -> str:
    return PAGE.format(corps="""<h1>Nouveau document</h1><p>Facture, appel de fonds, quittance, avis d'impôt ou de taxe foncière…</p>
<form action="/extraire" method="post" enctype="multipart/form-data">
<input type="file" name="photo" accept="image/*" capture="environment" required><button>Lire le document</button></form>""")


def _formulaire(doc: Document) -> str:
    alertes = valider(doc)
    lignes = "".join(f'<li class="{a.niveau}"><b>{a.champ}</b> : {html.escape(a.message)}</li>' for a in alertes) or "<li>Aucune alerte</li>"
    donnees = html.escape(doc.model_dump_json(indent=2))
    return PAGE.format(corps=f"""<h1>Relecture</h1><p>Vérifie chaque valeur contre la photo. Rien n'est envoyé tant que tu ne valides pas.</p>
<ul>{lignes}</ul>
<form action="/valider" method="post"><label>Données extraites (modifiables)
<textarea name="donnees" rows="40">{donnees}</textarea></label><button>Valider</button></form>""")


@app.post("/extraire", response_class=HTMLResponse)
async def extraire_photo(photo: UploadFile = File(...)) -> str:
    doc = app.state.extracteur(await photo.read(), photo.content_type or "image/jpeg")
    return _formulaire(doc)


@app.post("/valider", response_class=HTMLResponse)
def valider_saisie(donnees: str = Form(...)) -> str:
    doc = Document.model_validate_json(donnees)
    alertes = valider(doc)
    if any(a.niveau == "bloquant" for a in alertes):
        return _formulaire(doc)
    try:
        reference = app.state.destination.envoyer(doc)
    except Exception as erreur:
        tracer("envoi_document", "-", f"echec: {type(erreur).__name__}")
        return PAGE.format(corps=f"<h1>Non envoyé</h1><p>{html.escape(str(erreur))}</p><a href='/'>Retour</a>")
    tracer("envoi_document", reference, "ok")
    return PAGE.format(corps=f"<h1>Document envoyé au logiciel</h1><p>Référence : {html.escape(reference)}</p><a href='/'>Suivante</a>")
