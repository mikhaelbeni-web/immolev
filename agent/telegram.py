"""Pont Telegram : n'écoute que les membres autorisés, garde les photos en mémoire, demande un clic avant chaque écriture.

Lancer sur l'ordinateur du magasin :
    export TELEGRAM_TOKEN=...            # jeton du bot (@BotFather), dans le coffre de secrets
    export TELEGRAM_MEMBRES=123,456      # identifiants Telegram numériques autorisés
    export ANTHROPIC_API_KEY=...
    export CHROME_PROFIL=profil-chrome   # profil Chrome dédié, où l'opticien s'est connecté une fois
    export CONNECTEURS=connecteurs.json   # facultatif : connecteurs MCP (Gmail, Outlook…)
    export TELEGRAM_PHOTOS=0             # facultatif : refuser les photos d'ordonnance (acceptées par défaut, choix du 15/10)
    python3 -m agent.telegram
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx

from ordonnance.destination import Destination, LogicielNonConfigure, tracer

from .connecteurs_mcp import ConnecteursMCP
from . import fiche, regles
from .acces import dossier_donnees
from .membres import Registre
from .navigateur import Navigateur, outils_navigateur
from .orchestrateur import ActionEnAttente, Resultat, executer_confirmee, traiter
from .outils import Contexte, Outil, apercu_ordonnance, catalogue

DUREE_VIE_S = 3600


class ApiTelegram(Protocol):
    def appeler(self, methode: str, **params: Any) -> Any: ...
    def telecharger(self, file_id: str) -> bytes: ...


class ApiTelegramHttp:
    def __init__(self, jeton: str):
        self.base = f"https://api.telegram.org/bot{jeton}"
        self.fichiers = f"https://api.telegram.org/file/bot{jeton}"
        self.http = httpx.Client(timeout=60)

    def appeler(self, methode: str, **params: Any) -> Any:
        r = self.http.post(f"{self.base}/{methode}", json=params).json()
        if not r.get("ok"):
            raise RuntimeError(f"Telegram {methode} : {r.get('description')}")
        return r["result"]

    def telecharger(self, file_id: str) -> bytes:
        chemin = self.appeler("getFile", file_id=file_id)["file_path"]
        return self.http.get(f"{self.fichiers}/{chemin}").content


@dataclass
class Tache:
    numero: int
    chat_id: int
    demande: str
    appel: Callable[[], None] | None = None  # confirmation d'un bouton : passe avant les tâches en attente


@dataclass
class Pont:
    api: ApiTelegram
    membres: set[int]
    destination: Destination = field(default_factory=LogicielNonConfigure)
    traiter_demande: Callable[[str, dict[str, Outil]], Resultat] = traiter
    extracteur: Callable | None = None
    photos_autorisees: bool = False
    navigateur: Navigateur | None = None
    connecteurs: ConnecteursMCP | None = None
    transcrire: Callable[[bytes], str] | None = None  # messages vocaux → texte (agent/voix.py)
    registre: Registre | None = None  # demandes d'accès (agent/membres.py) ; sans lui, liste fixe
    relu: float = 0.0
    # File des tâches : l'écoute de Telegram continue pendant qu'une tâche longue tourne ; les demandes
    # s'empilent et sont traitées une par une, dans l'ordre (Playwright n'accepte qu'un fil d'exécution).
    asynchrone: bool = False
    file: list[Tache] = field(default_factory=list)
    en_cours: Tache | None = None
    numero: int = 0
    _cond: threading.Condition = field(default_factory=threading.Condition)
    _annoncees: set[int] = field(default_factory=set)
    contextes: dict[int, tuple[float, Contexte]] = field(default_factory=dict)
    actions: dict[str, tuple[int, ActionEnAttente]] = field(default_factory=dict)

    def _contexte(self, chat_id: int) -> Contexte:
        maintenant = time.time()
        for cid in [c for c, (t, _) in self.contextes.items() if maintenant - t > DUREE_VIE_S]:
            del self.contextes[cid]  # les photos ne survivent pas une heure
        _, ctx = self.contextes.get(chat_id, (0, Contexte()))
        self.contextes[chat_id] = (maintenant, ctx)
        return ctx

    def _outils(self, ctx: Contexte, chat_id: int | None = None) -> dict[str, Outil]:
        outils = catalogue(ctx, self.destination, self.extracteur) if self.extracteur else catalogue(ctx, self.destination)
        if self.navigateur:
            outils.update(outils_navigateur(self.navigateur))
        if self.connecteurs:
            outils.update(self.connecteurs.outils())
        outils["retenir_regle"] = Outil(
            "retenir_regle", "Ajoute une règle de fonctionnement du magasin, que tu appliqueras à toutes les demandes suivantes. "
            "Une ligne, sans nom ni donnée de patient.", {"regle": {"type": "string"}}, True, regles.ajouter)
        outils["completer_fiche"] = Outil(
            "completer_fiche", "Complète la fiche du magasin (questionnaire) avec une réponse donnée par l'équipe. "
            "question : identifiant de la question (ex. 'portails', 'equipe') ; reponse : une ou deux lignes, sans donnée de patient.",
            {"question": {"type": "string"}, "reponse": {"type": "string"}}, True, fiche.completer)
        outils["retenir_procedure"] = Outil(
            "retenir_procedure", "Retient les étapes exactes d'une tâche réussie sur un site (écrans, champs, boutons), pour la "
            "refaire sans chercher. nom : ex. 'MyEasyOptic : créer une fiche client'. Aucune donnée de client.",
            {"nom": {"type": "string"}, "etapes": {"type": "string"}}, True, fiche.retenir_procedure)
        if chat_id is not None:
            outils["ajouter_tache"] = Outil(
                "ajouter_tache", "Met une tâche dans la file : elle sera traitée seule, après la demande en cours. "
                "Sert quand un message contient plusieurs tâches indépendantes : garde la première, mets chacune des "
                "autres dans la file avec une consigne complète et autonome.", {"consigne": {"type": "string"}}, False,
                lambda consigne: self._mettre_en_file(chat_id, consigne))
        return outils

    def _envoyer(self, chat_id: int, texte: str, boutons: list[list[dict[str, str]]] | None = None) -> None:
        params: dict[str, Any] = {"chat_id": chat_id, "text": texte[:4000]}
        if boutons:
            params["reply_markup"] = {"inline_keyboard": boutons}
        self.api.appeler("sendMessage", **params)

    def traiter_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            return self._traiter_bouton(update["callback_query"])
        msg = update.get("message")
        if not msg:
            return
        auteur, chat_id = msg.get("from", {}).get("id"), msg["chat"]["id"]
        self._relire_membres(force=auteur not in self.membres)
        if auteur not in self.membres:
            tracer("telegram_refus", str(auteur), "membre_non_autorise")
            return self._demande_acces(msg)
        ctx = self._contexte(chat_id)
        demande = msg.get("text") or msg.get("caption") or ""
        vocal = msg.get("voice") or msg.get("audio") or msg.get("video_note")
        if vocal:
            if not self.transcrire:
                return self._envoyer(chat_id, "Les messages vocaux ne sont pas activés sur ce PC.")
            try:
                texte = self.transcrire(self.api.telecharger(vocal["file_id"]))
            except Exception as e:
                logging.exception("transcription")
                return self._envoyer(chat_id, f"Vocal non compris ({type(e).__name__}). Réessaie ou écris la demande.")
            if not texte:
                return self._envoyer(chat_id, "Je n'ai rien entendu dans ce vocal.")
            self._envoyer(chat_id, f"🎙️ Compris : « {texte} »")
            demande = f"{demande}\n{texte}".strip()
        if msg.get("photo") and not self.photos_autorisees:
            try:
                self.api.appeler("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])
            except Exception:
                pass
            return self._envoyer(chat_id, "Photo effacée : les ordonnances passent par la page web du magasin, pas par Telegram.")
        if msg.get("photo"):
            photo_id = f"photo{len(ctx.photos) + 1}"
            ctx.photos[photo_id] = (self.api.telecharger(msg["photo"][-1]["file_id"]), "image/jpeg")
            try:  # retire la photo du groupe une fois en mémoire (le bot doit être administrateur)
                self.api.appeler("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])
            except Exception:
                pass
            demande = f"{demande or 'Lis cette ordonnance et saisis-la dans MyEasyOptic.'}\n(Photo reçue : {photo_id})"
        if not demande:
            return
        commande = demande.strip().lower()
        if commande in ("/taches", "/tâches", "taches", "tâches", "/file"):
            return self._envoyer(chat_id, self._etat_file())
        if m := re.fullmatch(r"/?annuler\s+(?:la\s+)?(?:tâche\s+|tache\s+)?(?:n°\s*)?(\d+)", commande):
            return self._envoyer(chat_id, self._annuler(int(m.group(1))))
        with self._cond:
            self.numero += 1
            tache = Tache(self.numero, chat_id, demande)
            avant = len(self.file) + (1 if self.en_cours else 0)
            if self.asynchrone:
                if avant:
                    self._annoncees.add(tache.numero)
                self.file.append(tache)
                self._sauver()
                self._cond.notify()
        if not self.asynchrone:
            return self._executer(tache)
        if avant:
            self._envoyer(chat_id, f"📋 Noté : tâche n° {tache.numero}, {avant} avant elle. Je la traiterai ensuite. "
                                   "Envoie /taches pour voir la file, « annuler {n} » pour en retirer une.".replace("{n}", str(tache.numero)))

    def _executer(self, tache: Tache) -> None:
        chat_id, demande = tache.chat_id, tache.demande
        ctx = self._contexte(chat_id)
        recents = "".join(f"- Équipe : {d[:400]}\n- Toi : {r[:400]}\n" for d, r in ctx.echanges[-3:])
        complete = f"Échanges récents dans ce groupe :\n{recents}\nNouveau message : {demande}" if recents else demande
        resultat = self.traiter_demande(complete, self._outils(ctx, chat_id))
        ctx.echanges.append((demande, resultat.texte or "Fait."))
        del ctx.echanges[:-3]
        self._envoyer(chat_id, resultat.texte or "Fait.")
        for action in resultat.en_attente:
            self.actions[action.id] = (chat_id, action)
            ordo = ctx.ordonnances.get(action.parametres.get("photo_id", ""))
            apercu = f"\nVérifie contre l'ordonnance papier :\n{apercu_ordonnance(ordo)}" if ordo else ""
            if action.outil == "cliquer_bouton" and self.navigateur:
                try:
                    apercu = "\n" + self.navigateur.apercu_formulaire(action.parametres["ref"])
                except Exception:
                    apercu = "\n(aperçu indisponible)"
            self._envoyer(chat_id, f"À confirmer : {action.resume()}{apercu}",
                          [[{"text": "Confirmer", "callback_data": f"ok:{action.id}"}, {"text": "Annuler", "callback_data": f"non:{action.id}"}]])

    # file des tâches -------------------------------------------------------
    def _mettre_en_file(self, chat_id: int, consigne: str) -> str:
        with self._cond:
            self.numero += 1
            tache = Tache(self.numero, chat_id, consigne)
            self._annoncees.add(tache.numero)
            self.file.append(tache)
            self._sauver()
            self._cond.notify()
        if not self.asynchrone:
            return f"Tâche n° {tache.numero} notée (file non active dans ce mode)."
        return f"Tâche n° {tache.numero} ajoutée à la file."

    def _etat_file(self) -> str:
        with self._cond:
            lignes = ([f"▶️ En cours : n° {self.en_cours.numero} — {self.en_cours.demande[:80]}"] if self.en_cours and not self.en_cours.appel else [])
            lignes += [f"⏳ n° {t.numero} — {t.demande[:80]}" for t in self.file if not t.appel]
        return "\n".join(lignes) if lignes else "Aucune tâche en attente."

    def _annuler(self, numero: int) -> str:
        with self._cond:
            for t in self.file:
                if t.numero == numero and not t.appel:
                    self.file.remove(t)
                    self._sauver()
                    return f"Tâche n° {numero} retirée de la file."
        if self.en_cours and self.en_cours.numero == numero:
            return f"La tâche n° {numero} est déjà en cours : je ne peux pas l'interrompre."
        return f"Pas de tâche n° {numero} en attente."

    def _fichier_file(self):
        return dossier_donnees() / "taches.json"

    def _sauver(self) -> None:
        if not self.asynchrone:
            return
        restantes = ([self.en_cours] if self.en_cours else []) + self.file
        try:
            self._fichier_file().write_text(json.dumps(
                [{"numero": t.numero, "chat_id": t.chat_id, "demande": t.demande} for t in restantes if not t.appel],
                ensure_ascii=False), encoding="utf-8")
        except OSError:
            logging.exception("sauvegarde de la file")

    def _recharger(self) -> None:
        """Reprend les tâches restées en attente quand l'agent a été arrêté."""
        try:
            anciennes = json.loads(self._fichier_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for d in anciennes:
            self.numero = max(self.numero, d["numero"])
            self.file.append(Tache(d["numero"], d["chat_id"], d["demande"]))
        for chat in {t.chat_id for t in self.file}:
            n = sum(t.chat_id == chat for t in self.file)
            try:
                self._envoyer(chat, f"Je reprends {n} tâche(s) restée(s) en attente avant l'arrêt de l'agent.")
            except Exception:
                pass

    def _boucle_travail(self) -> None:
        while True:
            with self._cond:
                while not self.file:
                    self._cond.wait()
                tache = self.file.pop(0)
                self.en_cours = tache
                self._sauver()
            try:
                if tache.appel:
                    tache.appel()
                else:
                    if tache.numero in self._annoncees:
                        self._annoncees.discard(tache.numero)
                        self._envoyer(tache.chat_id, f"▶️ Je commence la tâche n° {tache.numero} : {tache.demande[:100]}")
                    self._executer(tache)
            except Exception as e:
                logging.exception("échec de la tâche")
                self._envoyer(tache.chat_id, message_erreur(e))
            finally:
                with self._cond:
                    self.en_cours = None
                    self._sauver()

    def _relire_membres(self, force: bool = False) -> None:
        """Prend en compte les personnes acceptées ou retirées depuis le panneau, sans redémarrer."""
        if self.registre and (force or time.time() - self.relu > 30):
            try:
                self.membres = self.registre.ids()
            except Exception:
                logging.exception("lecture des membres")
            self.relu = time.time()

    def _demande_acces(self, msg: dict[str, Any]) -> None:
        qui, chat = msg.get("from") or {}, msg["chat"]
        if not self.registre or qui.get("is_bot") or "id" not in qui:
            return
        demande = self.registre.noter_demande(qui, chat.get("title") or "message privé au bot")
        if not demande:
            return
        if chat.get("type") == "private":
            self._envoyer(chat["id"], "Demande d'accès envoyée au magasin. Vous pourrez m'écrire dès qu'elle sera acceptée.")
        pseudo = f" (@{demande['pseudo']})" if demande.get("pseudo") else ""
        for membre in self.membres:  # en privé : marche si le membre a déjà écrit au bot une fois
            try:
                self._envoyer(membre, f"Nouvelle demande d'accès : {demande['nom']}{pseudo}, depuis {demande['lieu']}.",
                              [[{"text": "Accepter", "callback_data": f"membre_ok:{demande['id']}"},
                                {"text": "Refuser", "callback_data": f"membre_non:{demande['id']}"}]])
            except Exception:
                pass

    def _decider_membre(self, cb: dict[str, Any], choix: str, ident: str) -> None:
        demande = self.registre.decider(ident, choix == "membre_ok") if self.registre else None
        chat = cb.get("message", {}).get("chat", {}).get("id") or cb["from"]["id"]
        if not demande:
            return self._envoyer(chat, "Cette demande a déjà été traitée.")
        self._relire_membres(force=True)
        tracer("membre", ident, f"{'accepte' if choix == 'membre_ok' else 'refuse'} par {cb['from']['id']}")
        if choix == "membre_ok":
            self._envoyer(chat, f"{demande['nom']} est autorisé(e).")
            try:
                from .orchestrateur import prenom
                nom = prenom()
                self._envoyer(int(ident), f"Accès accepté. Ici {nom}, l'agent Optizien du magasin : vous pouvez m'écrire."
                              if nom else "Accès accepté : vous pouvez m'écrire.")
            except Exception:
                pass
        else:
            self._envoyer(chat, f"Demande de {demande['nom']} refusée.")

    def _traiter_bouton(self, cb: dict[str, Any]) -> None:
        self.api.appeler("answerCallbackQuery", callback_query_id=cb["id"])
        self._relire_membres()
        if cb.get("from", {}).get("id") not in self.membres:
            return
        choix, _, action_id = cb.get("data", "").partition(":")
        if choix in ("membre_ok", "membre_non"):
            return self._decider_membre(cb, choix, action_id)
        if action_id not in self.actions:
            return
        chat_id, action = self.actions.pop(action_id)
        if choix != "ok":
            tracer(action.outil, action.id, "annulee")
            return self._envoyer(chat_id, f"Annulé : {action.outil}")
        qui = cb["from"]["id"]

        def executer() -> None:
            reponse = executer_confirmee(action, self._outils(self._contexte(chat_id)))
            tracer(action.outil, action.id, f"confirmee par {qui}")
            self._envoyer(chat_id, reponse)
        if not self.asynchrone:
            return executer()
        with self._cond:  # même fil que les tâches (Chrome), mais avant les tâches en attente
            self.file.insert(0, Tache(0, chat_id, f"confirmation {action.outil}", executer))
            self._cond.notify()
        if self.en_cours and not self.en_cours.appel:
            self._envoyer(chat_id, f"Confirmé : je l'exécute dès la fin de la tâche n° {self.en_cours.numero}.")

    def ecouter(self) -> None:
        """Écoute Telegram dans un fil à part ; les tâches tournent dans le fil principal (celui de Chrome)."""
        self.asynchrone = True
        self._recharger()
        threading.Thread(target=self._boucle_ecoute, daemon=True).start()
        self._boucle_travail()

    def _boucle_ecoute(self) -> None:
        decalage = 0
        while True:
            try:
                updates = self.api.appeler("getUpdates", offset=decalage, timeout=50)
            except Exception:  # coupure réseau : on réessaie, sans arrêter l'agent
                logging.exception("lecture Telegram")
                time.sleep(5)
                continue
            for update in updates:
                decalage = update["update_id"] + 1
                try:
                    self.traiter_update(update)
                except Exception as e:
                    logging.exception("échec du traitement")
                    chat = (update.get("message") or update.get("callback_query", {}).get("message") or {}).get("chat", {}).get("id")
                    if chat:
                        self._envoyer(chat, message_erreur(e))


def message_erreur(e: Exception) -> str:
    """Erreur lisible par l'équipe du magasin (le détail technique reste dans systeme/journal/agent.log)."""
    texte = str(e).lower()
    if "credit balance" in texte:
        return ("Plus de crédit sur le compte Claude : rechargez sur console.anthropic.com → Plans & Billing, "
                "puis renvoyez la demande.")
    if "authentication" in texte or "invalid x-api-key" in texte:
        return "La clé API Claude est refusée : vérifiez-la dans le panneau Optizien (carte Clé API)."
    if "overloaded" in texte or "rate limit" in texte or "rate_limit" in texte:
        return "Claude est surchargé pour le moment : réessayez dans une minute."
    return f"Erreur : {type(e).__name__} (détails dans le journal de l'agent)."


def voix_si_dispo() -> Callable[[bytes], str] | None:
    try:
        from . import voix
        import faster_whisper  # noqa: F401
    except ImportError:
        logging.warning("faster-whisper absent : messages vocaux désactivés")
        return None
    threading.Thread(target=voix.charger, daemon=True).start()  # premier vocal sans attente de chargement
    return voix.transcrire


def secret(nom: str) -> str:
    """Variable d'environnement, sinon coffre Windows rempli par configurer.py."""
    valeur = os.environ.get(nom)
    if not valeur:
        try:
            from . import coffre
            valeur = coffre.get_password("optizien", nom)
        except Exception:
            valeur = None
    if not valeur:
        raise SystemExit(f"{nom} manquant : ouvrir Optizien et compléter les réglages")
    return valeur


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for bavard in ("httpx", "httpx2", "httpcore"):  # leurs lignes contiennent le jeton du bot
        logging.getLogger(bavard).setLevel(logging.WARNING)
    try:  # compte Optizien : l'agent passe par la passerelle du site, sans clé API sur ce PC
        from . import passerelle
        compte = json.loads(secret("OPTIZIEN_COMPTE"))
        os.environ.update(passerelle.environnement(compte))
    except SystemExit:  # pas de compte : ancienne installation avec sa propre clé
        os.environ["ANTHROPIC_API_KEY"] = secret("ANTHROPIC_API_KEY")
    membres = {int(m) for m in secret("TELEGRAM_MEMBRES").split(",") if m.strip()}
    nav = Navigateur.lancer(os.environ.get("CHROME_PROFIL", "profil-chrome"))
    connecteurs = ConnecteursMCP.depuis_fichier(os.environ["CONNECTEURS"]) if os.environ.get("CONNECTEURS") else None
    if connecteurs:
        logging.info("Connecteurs MCP :\n%s", connecteurs.etat())
    Pont(ApiTelegramHttp(secret("TELEGRAM_TOKEN")), membres, photos_autorisees=os.environ.get("TELEGRAM_PHOTOS", "1") == "1",
         navigateur=nav, connecteurs=connecteurs, transcrire=voix_si_dispo(), registre=Registre(dossier_donnees())).ecouter()
