"""Pont Telegram : n'écoute que les membres autorisés, garde les photos en mémoire, demande un clic avant chaque écriture.

Lancer sur l'ordinateur du gestionnaire :
    export TELEGRAM_TOKEN=...            # jeton du bot (@BotFather), dans le coffre de secrets
    export TELEGRAM_MEMBRES=123,456      # identifiants Telegram numériques autorisés
    export ANTHROPIC_API_KEY=...
    export CHROME_PROFIL=profil-chrome   # profil Chrome dédié, où le gestionnaire s'est connecté une fois
    export CONNECTEURS=connecteurs.json   # facultatif : connecteurs MCP (Gmail, Outlook…)
    export TELEGRAM_PHOTOS=0             # facultatif : refuser les photos de documents (acceptées par défaut, choix du 15/10)
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

from document.destination import Destination, LogicielNonConfigure, tracer

from .connecteurs_mcp import ConnecteursMCP
from . import fiche, patrimoine, programmees, regles
from .bureau import BUREAU, Bureau
from .acces import dossier_donnees
from .membres import Registre
from .navigateur import Navigateur, outils_navigateur
from .orchestrateur import ActionEnAttente, Resultat, executer_confirmee, traiter
from .outils import Contexte, Outil, apercu_document, catalogue

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


MOTS_OUI = {"confirmé", "confirme", "confirmer", "oui", "ok", "valide", "validé", "c'est bon", "vas-y", "go", "d'accord"}
MOTS_NON = {"non", "annule", "annuler", "annulé", "stop"}


def _echanges_recents(echanges: list[tuple[str, str]]) -> str:
    """Derniers échanges du groupe pour le modèle. Le dernier est gardé en entier : une réponse courte (« C », « oui »)
    renvoie à la fin de ta dernière réponse, là où se trouvent les options. Les plus anciens sont raccourcis."""
    lignes = []
    for i, (d, r) in enumerate(echanges[-3:], start=1):
        dernier = i == len(echanges[-3:])
        lignes.append(f"- Équipe : {d[:1500 if dernier else 400]}\n- Toi : {r[:4000 if dernier else 600]}\n")
    return "".join(lignes)


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
    bureau: Bureau | None = None  # discussion depuis le panneau (agent/bureau.py)
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
    actions_le: dict[str, float] = field(default_factory=dict)

    def _contexte(self, chat_id: int) -> Contexte:
        maintenant = time.time()
        for cid in [c for c, (t, _) in self.contextes.items() if maintenant - t > DUREE_VIE_S]:
            del self.contextes[cid]  # les photos ne survivent pas une heure
        if chat_id not in self.contextes:
            self.contextes[chat_id] = (maintenant, Contexte(echanges=self._echanges_gardes(chat_id)))
        _, ctx = self.contextes[chat_id]
        self.contextes[chat_id] = (maintenant, ctx)
        return ctx

    def _fichier_echanges(self):
        return dossier_donnees() / "echanges.json"

    def _echanges_gardes(self, chat_id: int) -> list[tuple[str, str]]:
        """Derniers échanges du groupe, gardés sur disque : un redémarrage de l'agent ne les efface plus (6 h)."""
        if not self.asynchrone:
            return []
        try:
            d = json.loads(self._fichier_echanges().read_text(encoding="utf-8")).get(str(chat_id), {})
        except (OSError, ValueError):
            return []
        return [(a, b) for a, b in d.get("echanges", [])] if time.time() - d.get("le", 0) < 21600 else []

    def _garder_echanges(self, chat_id: int, echanges: list[tuple[str, str]]) -> None:
        if not self.asynchrone:
            return
        try:
            f = self._fichier_echanges()
            try:
                tout = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                tout = {}
            tout[str(chat_id)] = {"le": time.time(), "echanges": [[a[:1500], b[:4000]] for a, b in echanges[-3:]]}
            f.write_text(json.dumps(tout, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logging.exception("sauvegarde des échanges")

    def _outils(self, ctx: Contexte, chat_id: int | None = None) -> dict[str, Outil]:
        outils = catalogue(ctx, self.destination, self.extracteur) if self.extracteur else catalogue(ctx, self.destination)
        if self.navigateur:
            outils.update(outils_navigateur(self.navigateur))
        if self.connecteurs:
            outils.update(self.connecteurs.outils())
        outils["retenir_regle"] = Outil(
            "retenir_regle", "Ajoute une règle de fonctionnement du gestionnaire, que tu appliqueras à toutes les demandes suivantes. "
            "Une ligne, sans nom ni donnée personnelle.", {"regle": {"type": "string"}}, True, regles.ajouter)
        outils["completer_fiche"] = Outil(
            "completer_fiche", "Complète la fiche du gestionnaire (questionnaire) avec une réponse donnée par l'équipe. "
            "question : identifiant de la question (ex. 'contacts_equipe', 'banques') ; reponse : une ou deux lignes, sans mot de passe, IBAN ni numéro fiscal.",
            {"question": {"type": "string"}, "reponse": {"type": "string"}}, True, fiche.completer)
        outils["retenir_procedure"] = Outil(
            "retenir_procedure", "Retient les étapes exactes d'une tâche réussie sur un site (écrans, champs, boutons), pour la "
            "refaire sans chercher. nom : ex. 'Logiciel copro : saisir une facture fournisseur'. Aucune donnée personnelle.",
            {"nom": {"type": "string"}, "etapes": {"type": "string"}}, True, fiche.retenir_procedure)
        outils["consulter_patrimoine"] = Outil(
            "consulter_patrimoine", "Caractéristiques exactes des appartements et locaux gérés (surface Carrez ou au sol, "
            "type, chambres, salles de bain, étage) et chemin de chaque plan dans le OneDrive. À consulter avant de donner "
            "une surface ou d'envoyer un plan. recherche : immeuble et/ou lot, ex. 'sevres 2G', 'commerce', '' pour la liste.",
            {"recherche": {"type": "string"}}, False, lambda recherche="": patrimoine.consulter(dossier_donnees(), recherche))
        outils["noter_site"] = Outil(
            "noter_site", "Note une information technique sur un site pour la prochaine fois : méthode de connexion qui marche, "
            "erreur déjà vue et sa solution, étape qui demande l'équipe (captcha, code SMS). Une ligne, aucun identifiant ni donnée de client.",
            {"site": {"type": "string"}, "note": {"type": "string"}}, False, fiche.noter_site)
        if chat_id is not None:
            outils["ajouter_tache"] = Outil(
                "ajouter_tache", "Met une tâche dans la file : elle sera traitée seule, après la demande en cours. "
                "Sert quand un message contient plusieurs tâches indépendantes : garde la première, mets chacune des "
                "autres dans la file avec une consigne complète et autonome.", {"consigne": {"type": "string"}}, False,
                lambda consigne: self._mettre_en_file(chat_id, consigne))
            outils["programmer_tache"] = Outil(
                "programmer_tache", "Programme une tâche répétitive que tu feras seul à l'heure dite, quand le gestionnaire "
                "le demande (« chaque lundi à 9 h… », « tous les matins… », « le 5 de chaque mois… »). consigne : complète et "
                "autonome, comme si tu la recevais sans contexte. frequence : jour, ouvre (lundi-vendredi), semaine ou mois. "
                "heure : HH:MM. jour_semaine : lundi…dimanche si semaine, sinon \"\". jour_mois : 1-31 si mois (31 = dernier "
                "jour), sinon 0. Le résultat arrivera dans cette conversation ; les actions qui enregistrent ou envoient "
                "demanderont toujours confirmation.",
                {"consigne": {"type": "string"}, "frequence": {"type": "string", "enum": list(programmees.FREQUENCES)},
                 "heure": {"type": "string"}, "jour_semaine": {"type": "string"}, "jour_mois": {"type": "integer"}}, False,
                lambda consigne, frequence, heure, jour_semaine="", jour_mois=0: self._programmer(
                    chat_id, consigne, frequence, heure, jour_semaine, jour_mois))
            outils["taches_programmees"] = Outil(
                "taches_programmees", "Liste les tâches répétitives programmées (identifiant, quand, consigne).", {}, False,
                lambda: programmees.resume(dossier_donnees()))
            outils["arreter_tache_programmee"] = Outil(
                "arreter_tache_programmee", "Supprime une tâche répétitive (identifiant donné par taches_programmees).",
                {"id": {"type": "string"}}, False,
                lambda id: "Tâche répétitive supprimée." if programmees.modifier(dossier_donnees(), id, supprimer=True)
                else "Identifiant inconnu : appelle taches_programmees.")
        return outils

    def _envoyer(self, chat_id: int, texte: str, boutons: list[list[dict[str, str]]] | None = None) -> None:
        if chat_id == BUREAU and self.bureau:
            return self.bureau.ecrire(texte, boutons)
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
        depuis_bureau = chat_id == BUREAU and auteur == BUREAU and self.bureau is not None
        if not depuis_bureau:
            self._relire_membres(force=auteur not in self.membres)
        if auteur not in self.membres and not depuis_bureau:
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
                return self._envoyer(chat_id, "Je n'ai pas pu écouter ce vocal (le modèle vocal du PC n'a pas répondu). "
                                              "Écris la demande en texte ; je réessaierai le prochain vocal.")
            if not texte:
                return self._envoyer(chat_id, "Je n'ai rien entendu dans ce vocal.")
            self._envoyer(chat_id, f"🎙️ Compris : « {texte} »")
            demande = f"{demande}\n{texte}".strip()
        if msg.get("photo") and not self.photos_autorisees:
            try:
                self.api.appeler("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])
            except Exception:
                pass
            return self._envoyer(chat_id, "Photo effacée : les documents passent par la page web d'Immolev, pas par Telegram.")
        if msg.get("photo"):
            photo_id = f"photo{len(ctx.photos) + 1}"
            ctx.photos[photo_id] = (self.api.telecharger(msg["photo"][-1]["file_id"]), "image/jpeg")
            try:  # retire la photo du groupe une fois en mémoire (le bot doit être administrateur)
                self.api.appeler("deleteMessage", chat_id=chat_id, message_id=msg["message_id"])
            except Exception:
                pass
            demande = f"{demande or 'Lis ce document, contrôle-le et prépare son classement.'}\n(Photo reçue : {photo_id})"
        if not demande:
            return
        commande = demande.strip().lower()
        if (oui := commande.strip(" .!") in MOTS_OUI) or commande.strip(" .!") in MOTS_NON:
            attente = [i for i, (c, _) in self.actions.items() if c == chat_id]
            if attente:  # un mot de confirmation vaut un clic sur le dernier bouton de ce groupe
                return self._confirmer(attente[-1], oui, auteur)
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

    def _conversation(self, chat_id: int) -> str:
        """Privée, groupe sans autre personne, ou groupe partagé : décide si l'agent peut y donner des données sensibles."""
        if chat_id == BUREAU:
            return "privée (le gestionnaire t'écrit depuis le panneau Immolev sur son PC)"
        if chat_id > 0:  # Telegram : identifiant positif = conversation privée avec le bot
            return "privée"
        cache = self.__dict__.setdefault("_membres_groupe", {})
        nombre, le = cache.get(chat_id, (None, 0.0))
        if nombre is None or time.time() - le > 600:
            try:
                nombre = int(self.api.appeler("getChatMemberCount", chat_id=chat_id))
            except Exception:
                logging.exception("nombre de membres du groupe")
                nombre = None
            cache[chat_id] = (nombre, time.time())
        if nombre is None:
            return "groupe (nombre de membres inconnu : traite-le comme partagé)"
        if nombre <= 2:  # la personne qui écrit + le bot
            return "groupe sans autre personne (seulement la personne qui écrit et toi) : même confidentialité qu'en privé"
        return f"groupe partagé ({nombre - 1} personnes)"

    def _executer(self, tache: Tache) -> None:
        chat_id, demande = tache.chat_id, tache.demande
        ctx = self._contexte(chat_id)
        recents = _echanges_recents(ctx.echanges)
        conversation = f"Conversation : {self._conversation(chat_id)}\n"
        complete = conversation + (f"Échanges récents dans cette conversation :\n{recents}\nNouveau message : {demande}" if recents else demande)
        resultat = self.traiter_demande(complete, self._outils(ctx, chat_id))
        ctx.echanges.append((demande, resultat.texte or "Fait."))
        del ctx.echanges[:-3]
        self._garder_echanges(chat_id, ctx.echanges)
        self._envoyer(chat_id, resultat.texte or "Fait.")
        for a in resultat.en_attente:
            logging.info("EN ATTENTE de confirmation : %s %s", a.outil, json.dumps(a.parametres, ensure_ascii=False)[:300])
        for action in resultat.en_attente:
            self.actions[action.id] = (chat_id, action)
            self.actions_le[action.id] = time.time()
            self._sauver_actions()
            doc = ctx.documents.get(action.parametres.get("photo_id", ""))
            apercu = f"\nVérifie contre le document papier :\n{apercu_document(doc)}" if doc else ""
            if action.outil == "cliquer_bouton" and self.navigateur:
                try:
                    action.parametres.setdefault("libelle", self.navigateur.libelle(action.parametres["ref"]))
                    apercu = "\n" + self.navigateur.apercu_formulaire(action.parametres["ref"])
                    self._sauver_actions()
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

    def _programmer(self, chat_id: int, consigne: str, frequence: str, heure: str, jour_semaine: str, jour_mois: int) -> str:
        try:
            t = programmees.ajouter(dossier_donnees(), consigne, frequence, heure, jour_semaine, jour_mois, chat_id)
        except ValueError as e:
            return f"Non programmée : {e}"
        return (f"Tâche répétitive programmée [{t['id']}] : {programmees.description(t)}. Elle tourne tant que l'agent est "
                "démarré ; si le PC est éteint à l'heure prévue, elle est faite au démarrage suivant. Visible dans le panneau.")

    def _boucle_programmees(self) -> None:
        while True:
            try:
                for t, en_retard in programmees.a_lancer(dossier_donnees()):
                    retard = " (en retard : le PC ou l'agent était arrêté à l'heure prévue)" if en_retard else ""
                    logging.info("TÂCHE PROGRAMMÉE %s : %s", t["id"], t["consigne"][:200])
                    self._mettre_en_file(int(t.get("chat_id", BUREAU)),
                                         f"Tâche répétitive programmée ({programmees.description(t)}){retard} : {t['consigne']}")
            except Exception:
                logging.exception("tâches programmées")
            time.sleep(30)

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

    def _sauver_actions(self) -> None:
        try:
            (dossier_donnees() / "actions-en-attente.json").write_text(json.dumps(
                [{"chat_id": c, "id": a.id, "outil": a.outil, "parametres": a.parametres, "le": t}
                 for c, a, t in self._horodatees()], ensure_ascii=False), encoding="utf-8")
        except OSError:
            logging.exception("sauvegarde des actions en attente")

    def _horodatees(self):
        return [(c, a, self.actions_le.get(a.id, time.time())) for c, a in self.actions.values()]

    def _recharger_actions(self) -> None:
        """Les boutons « Confirmer » restent valables après un redémarrage de l'agent (2 h)."""
        try:
            anciennes = json.loads((dossier_donnees() / "actions-en-attente.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for d in anciennes:
            if time.time() - d.get("le", 0) < 7200:
                self.actions[d["id"]] = (d["chat_id"], ActionEnAttente(d["id"], d["outil"], d["parametres"]))
                self.actions_le[d["id"]] = d["le"]

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
            self._envoyer(chat["id"], "Demande d'accès envoyée au gestionnaire. Vous pourrez m'écrire dès qu'elle sera acceptée.")
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
                self._envoyer(int(ident), f"Accès accepté. Ici {nom}, l'agent Immolev : vous pouvez m'écrire."
                              if nom else "Accès accepté : vous pouvez m'écrire.")
            except Exception:
                pass
        else:
            self._envoyer(chat, f"Demande de {demande['nom']} refusée.")

    def _repondre_bouton(self, cb_id: str, **params: Any) -> None:
        """Arrête le sablier du bouton. Un échec (clic ancien, réseau coupé) ne doit jamais bloquer l'action."""
        if cb_id == "bureau":
            return
        try:
            self.api.appeler("answerCallbackQuery", callback_query_id=cb_id, **params)
        except Exception:
            logging.warning("réponse au bouton impossible", exc_info=True)

    def _traiter_bouton(self, cb: dict[str, Any]) -> None:
        self._relire_membres()
        bureau = cb.get("id") == "bureau" and cb.get("from", {}).get("id") == BUREAU and self.bureau is not None
        if cb.get("from", {}).get("id") not in self.membres and not bureau:
            return self._repondre_bouton(cb["id"])
        choix, _, action_id = cb.get("data", "").partition(":")
        if choix in ("membre_ok", "membre_non"):
            self._repondre_bouton(cb["id"])
            return self._decider_membre(cb, choix, action_id)
        chat = (cb.get("message") or {}).get("chat", {}).get("id")
        if action_id not in self.actions:
            self._repondre_bouton(cb["id"], text="Cette demande n'est plus active.")
            if chat:
                self._envoyer(chat, "Ce bouton n'est plus actif (demande déjà traitée ou trop ancienne). "
                                    "Redemande l'action et je te renverrai un nouveau bouton.")
            return
        self._repondre_bouton(cb["id"],
                         text="Reçu, j'exécute…" if choix == "ok" else "Annulé.")
        self._confirmer(action_id, choix == "ok", cb["from"]["id"])

    def _confirmer(self, action_id: str, accepte: bool, qui: int) -> None:
        chat_id, action = self.actions.pop(action_id)
        self.actions_le.pop(action_id, None)
        self._sauver_actions()
        if not accepte:
            tracer(action.outil, action.id, "annulee")
            return self._envoyer(chat_id, f"Annulé : {action.outil}")

        def executer() -> None:
            reponse = executer_confirmee(action, self._outils(self._contexte(chat_id)))
            tracer(action.outil, action.id, f"confirmee par {qui} : {reponse[:200]}")
            self._envoyer(chat_id, reponse)
        if not self.asynchrone:
            return executer()
        with self._cond:  # même fil que les tâches (Chrome), mais avant les tâches en attente
            self.file.insert(0, Tache(0, chat_id, f"confirmation {action.outil}", executer))
            self._cond.notify()
        if self.en_cours and not self.en_cours.appel:
            self._envoyer(chat_id, f"Confirmé : je l'exécute dès la fin de la tâche n° {self.en_cours.numero}.")
        else:
            self._envoyer(chat_id, "⏳ Confirmé, j'exécute…")

    def ecouter(self) -> None:
        """Écoute Telegram dans un fil à part ; les tâches tournent dans le fil principal (celui de Chrome)."""
        self.asynchrone = True
        self._recharger()
        self._recharger_actions()
        threading.Thread(target=self._boucle_ecoute, daemon=True).start()
        if self.bureau:
            threading.Thread(target=self._boucle_bureau, daemon=True).start()
        threading.Thread(target=self._boucle_programmees, daemon=True).start()
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
                        logging.error("Message d'erreur envoyé sur Telegram : %s", message_erreur(e))
                        self._envoyer(chat, message_erreur(e))


    def _boucle_bureau(self) -> None:
        while True:
            for update in self.bureau.nouvelles():
                try:
                    self.traiter_update(update)
                except Exception as e:
                    logging.exception("échec du traitement (bureau)")
                    self._envoyer(BUREAU, message_erreur(e))
            time.sleep(0.7)


def message_erreur(e: Exception) -> str:
    """Erreur lisible par l'équipe du gestionnaire (le détail technique reste dans systeme/journal/agent.log)."""
    texte = str(e).lower()
    if "credit balance" in texte:
        return ("Plus de crédit sur le compte Claude : rechargez sur console.anthropic.com → Plans & Billing, "
                "puis renvoyez la demande.")
    if "authentication" in texte or "invalid x-api-key" in texte:
        return "La clé API Claude est refusée : vérifiez-la dans le panneau Immolev (carte Clé API)."
    code = getattr(e, "status_code", None)
    if code == 429 or "rate limit" in texte or "rate_limit" in texte:
        return ("Limite de débit du compte Claude atteinte (trop de texte lu d'un coup) : j'ai attendu près de deux minutes sans succès. "
                "Renvoie la demande, si possible plus ciblée (une seule boîte mail, une période).")
    if code == 529 or "overloaded" in texte:
        return "Claude est surchargé chez Anthropic : j'ai réessayé pendant près de deux minutes. Renvoie la demande un peu plus tard."
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
            valeur = coffre.get_password("immolev", nom)
        except Exception:
            valeur = None
    if not valeur:
        raise SystemExit(f"{nom} manquant : ouvrir Immolev et compléter les réglages")
    return valeur


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%d/%m %H:%M:%S")
    for bavard in ("httpx", "httpx2", "httpcore"):  # leurs lignes contiennent le jeton du bot
        logging.getLogger(bavard).setLevel(logging.WARNING)
    try:  # compte Immolev : l'agent passe par la passerelle du site, sans clé API sur ce PC
        from . import passerelle
        compte = json.loads(secret("IMMOLEV_COMPTE"))
        os.environ.update(passerelle.environnement(compte))
    except SystemExit:  # pas de compte : ancienne installation avec sa propre clé
        os.environ["ANTHROPIC_API_KEY"] = secret("ANTHROPIC_API_KEY")
    membres = {int(m) for m in secret("TELEGRAM_MEMBRES").split(",") if m.strip()}
    nav = Navigateur.lancer(os.environ.get("CHROME_PROFIL", "profil-chrome"))
    connecteurs = ConnecteursMCP.depuis_fichier(os.environ["CONNECTEURS"]) if os.environ.get("CONNECTEURS") else None
    if connecteurs:
        logging.info("Connecteurs MCP :\n%s", connecteurs.etat())
    Pont(ApiTelegramHttp(secret("TELEGRAM_TOKEN")), membres, photos_autorisees=os.environ.get("TELEGRAM_PHOTOS", "1") == "1",
         navigateur=nav, connecteurs=connecteurs, transcrire=voix_si_dispo(), registre=Registre(dossier_donnees()),
         bureau=Bureau(dossier_donnees())).ecouter()
