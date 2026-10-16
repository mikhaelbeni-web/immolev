"""Branche des logiciels externes (Gmail, Outlook/Hotmail, agenda, stockage…) par MCP.

Chaque serveur déclaré dans `connecteurs.json` est lancé (ou joint par URL), ses outils sont
proposés à Claude sous le nom `<serveur>__<outil>`. Un outil n'est en lecture libre que si le
serveur le déclare en lecture seule (readOnlyHint) ou si la configuration le liste dans "lecture".
Tout le reste (envoyer, supprimer, créer, modifier…) attend la confirmation de l'opticien.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from .outils import Outil

DELAI_S = 120


def _texte(resultat: Any) -> str:
    morceaux = []
    for c in getattr(resultat, "content", []) or []:
        morceaux.append(c.text if getattr(c, "type", "") == "text" else f"[contenu {getattr(c, 'type', '?')} non affiché]")
    texte = "\n".join(morceaux) or json.dumps(getattr(resultat, "structured_content", None), ensure_ascii=False)
    return ("Erreur du connecteur : " + texte) if getattr(resultat, "is_error", False) else texte


class ConnecteursMCP:
    """Garde les sessions MCP ouvertes dans une boucle asyncio en arrière-plan ; appels synchrones pour l'agent."""

    def __init__(self, config: dict[str, dict[str, Any]]):
        self.config = config
        self.sessions: dict[str, ClientSession] = {}
        self.outils_bruts: dict[str, list[Any]] = {}
        self.erreurs: dict[str, str] = {}
        self._boucle = asyncio.new_event_loop()
        self._fil = threading.Thread(target=self._boucle.run_forever, daemon=True)
        self._fil.start()
        self._arret: asyncio.Event = self._executer(self._creer_evenement())
        self._taches = []
        for nom in config:
            pret = threading.Event()
            self._taches.append(asyncio.run_coroutine_threadsafe(self._tenir(nom, pret), self._boucle))
            pret.wait(DELAI_S)

    @classmethod
    def depuis_fichier(cls, chemin: str | Path) -> "ConnecteursMCP":
        brut = Path(chemin).read_text()
        # ${VAR} est remplacé par la variable d'environnement : aucun jeton n'est écrit dans le fichier
        brut = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), brut)
        return cls({k: v for k, v in json.loads(brut).items() if not k.startswith("_")})

    def _executer(self, coro: Any, delai: float = DELAI_S) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._boucle).result(delai)

    async def _creer_evenement(self) -> asyncio.Event:
        return asyncio.Event()

    async def _tenir(self, nom: str, pret: threading.Event) -> None:
        """Ouvre la session d'un serveur et la garde ouverte jusqu'à l'arrêt, dans une seule tâche."""
        conf = self.config[nom]
        try:
            async with AsyncExitStack() as pile:
                if "url" in conf:
                    http = await pile.enter_async_context(create_mcp_http_client(headers=conf.get("entetes")))
                    flux = await pile.enter_async_context(streamable_http_client(conf["url"], http_client=http))
                    lecture, ecriture = flux[0], flux[1]
                else:
                    commande = sys.executable if conf["commande"] in ("python", "python3") else conf["commande"]  # même Python que l'agent
                    params = StdioServerParameters(command=commande, args=conf.get("args", []), env={**os.environ, **conf.get("env", {})})
                    lecture, ecriture = await pile.enter_async_context(stdio_client(params))
                session = await pile.enter_async_context(ClientSession(lecture, ecriture))
                await session.initialize()
                self.outils_bruts[nom] = (await session.list_tools()).tools
                self.sessions[nom] = session
                pret.set()
                await self._arret.wait()
        except BaseException as e:  # un connecteur en panne ne bloque pas les autres
            if nom not in self.sessions:
                self.erreurs[nom] = f"{type(e).__name__}: {e}"
        finally:
            pret.set()

    def appeler(self, serveur: str, outil: str, arguments: dict[str, Any]) -> str:
        return _texte(self._executer(self.sessions[serveur].call_tool(outil, arguments)))

    def outils(self) -> dict[str, Outil]:
        resultat: dict[str, Outil] = {}
        for serveur, liste in self.outils_bruts.items():
            conf = self.config[serveur]
            for t in liste:
                lecture_seule = bool(t.annotations and t.annotations.read_only_hint)
                if t.name in conf.get("lecture", []):
                    lecture_seule = True
                if t.name in conf.get("ecriture", []):
                    lecture_seule = False
                nom = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{serveur}__{t.name}")[:64]
                resultat[nom] = Outil(
                    nom=nom,
                    description=f"[{serveur}] {t.description or t.name}",
                    parametres={},
                    ecriture=not lecture_seule,
                    executer=lambda _s=serveur, _t=t.name, **args: self.appeler(_s, _t, args),
                    schema=t.input_schema or {"type": "object", "properties": {}},
                )
        return resultat

    def etat(self) -> str:
        lignes = [f"{n} : {len(o)} outils" for n, o in self.outils_bruts.items()]
        lignes += [f"{n} : HORS SERVICE ({e})" for n, e in self.erreurs.items()]
        return "\n".join(lignes) or "Aucun connecteur"

    def fermer(self) -> None:
        self._boucle.call_soon_threadsafe(self._arret.set)
        for t in self._taches:
            try:
                t.result(30)
            except Exception:
                pass
        self._boucle.call_soon_threadsafe(self._boucle.stop)
