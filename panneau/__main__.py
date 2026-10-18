"""Panneau Immolev : installation, réglages et marche/arrêt de l'agent, sans ligne de commande.

Lancé par « Démarrer Immolev » (pythonw -m panneau). N'utilise que la bibliothèque standard
tant que les composants ne sont pas installés. Écoute seulement 127.0.0.1, avec un jeton.

    -m panneau           ouvre le panneau
    -m panneau --agent   démarre l'agent s'il est configuré (démarrage de Windows), sans fenêtre
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import base64

from . import maj, systeme, visage
from .messagerie import Messagerie

APP = Path(__file__).resolve().parent.parent
SYSTEME = APP.parent
JOURNAL_DIR = SYSTEME / "journal"
DONNEES = Path(os.environ.get("IMMOLEV_DONNEES") or
               Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "Immolev")
EXIGENCES = APP / "requirements-agent.txt"
SERVICE = "immolev"
PAGE = Path(__file__).with_name("page.html")
ICONE = Path(__file__).with_name("immolev.ico")


# ---------------------------------------------------------------- secrets (coffre Windows)

def charger_composants() -> None:
    """Rend utilisables les paquets installés après le lancement du panneau, y compris leurs fichiers .pth
    (pywin32 : sans eux, « No module named 'pywintypes' »)."""
    import site
    importlib.invalidate_caches()
    for dossier in site.getsitepackages():
        site.addsitedir(dossier)


def _keyring():
    from agent import coffre  # coffre Windows, sinon fichier chiffré par Windows
    return coffre


def lire_secret(nom: str) -> str | None:
    try:
        return _keyring().get_password(SERVICE, nom)
    except Exception:
        return None


def ecrire_secret(nom: str, valeur: str) -> None:
    _keyring().set_password(SERVICE, nom, valeur)


def apercu(valeur: str | None, debut: int = 13) -> str | None:
    return f"{valeur[:debut]}…{valeur[-4:]}" if valeur else None


def propre(valeur: str) -> str:
    valeur = (valeur or "").strip()
    if not valeur:
        raise ValueError("Rien n'a été collé.")
    if len(valeur) > 300 or re.search(r"\s", valeur):
        raise ValueError(f"Ce texte fait {len(valeur)} caractères avec des espaces : ce n'est pas une clé. "
                         "Recopiez uniquement la clé.")
    return valeur


# ---------------------------------------------------------------- vérifications en ligne

def _http_json(url: str, entetes: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=entetes or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def verifier_cle(cle: str) -> dict:
    """Liste des modèles : gratuit, ne consomme aucun crédit."""
    try:
        code, rep = _http_json("https://api.anthropic.com/v1/models?limit=1",
                             {"x-api-key": cle, "anthropic-version": "2023-06-01"})
    except OSError as e:
        return {"ok": None, "message": f"Vérification impossible (réseau) : {e}"}
    if code == 200:
        return {"ok": True, "message": "Clé acceptée par Anthropic."}
    if code in (401, 403):
        return {"ok": False, "message": "Anthropic refuse cette clé. Il faut une clé « API Keys » de "
                                        "console.anthropic.com (elle commence par sk-ant-api)."}
    detail = str((rep.get("error") or {}).get("message") or "")
    if "credit balance" in detail.lower():
        return {"ok": None, "message": "Clé enregistrée, mais le compte n'a plus de crédit : rechargez sur "
                                       "console.anthropic.com → Plans & Billing, puis cliquez sur Actualiser."}
    if code == 429:
        return {"ok": None, "message": "Anthropic limite les appels pour le moment : cliquez sur Actualiser dans une minute."}
    return {"ok": None, "message": f"Clé enregistrée, mais Anthropic répond une erreur ({code}) : {detail[:200] or 'sans détail'}."}


def telegram(jeton: str, methode: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{jeton}/{methode}"
    if params:
        url += "?" + urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                                             for k, v in params.items()})
    try:
        code, rep = _http_json(url, timeout=30)
    except OSError as e:
        return {"ok": False, "description": f"réseau : {e}"}
    rep.setdefault("ok", code == 200)
    return rep


def verifier_bot(jeton: str) -> dict:
    rep = telegram(jeton, "getMe")
    if not rep.get("ok"):
        if "réseau" in str(rep.get("description", "")):
            return {"ok": None, "message": f"Vérification impossible ({rep['description']})."}
        return {"ok": False, "message": "Telegram refuse ce jeton. Recopiez la ligne donnée par @BotFather "
                                        "(du type 123456789:AAH…)."}
    bot = rep["result"]
    return {"ok": True, "nom": "@" + bot.get("username", "?"),
            "lit_groupe": bool(bot.get("can_read_all_group_messages")),
            "message": f"Bot reconnu : @{bot.get('username')}"}


# ---------------------------------------------------------------- état local

def comptes_chrome(profil: Path) -> list[str]:
    """Adresses Google connectées dans le profil Chrome de l'agent (lues dans ses Preferences, sans rien envoyer)."""
    try:
        pref = json.loads((profil / "Default" / "Preferences").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    brut = [a.get("email", "") for a in pref.get("account_info", []) if isinstance(a, dict)]
    brut += re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", str((pref.get("gaia_cookie") or {}).get("last_list_accounts_data", "")))
    return list(dict.fromkeys(a.lower() for a in brut if "@" in a))


class Etat:
    def __init__(self):
        DONNEES.mkdir(parents=True, exist_ok=True)
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        self.verrou = threading.Lock()
        self.installation = {"en_cours": False, "progression": 0, "ligne": "", "erreur": None}
        self.verif_cle: dict | None = None
        self.verif_bot: dict | None = None
        self.dernier_ping = time.time()
        self.messagerie = Messagerie(DONNEES, APP, JOURNAL_DIR)
        self.messagerie.apres_changement = self.redemarrer_si_en_marche
        self.version = maj.version_de(APP)
        self._maj_cache: tuple[float, dict | None] = (0, None)
        self._maj_en_ligne: dict | None = None
        threading.Thread(target=self._boucle_en_ligne, daemon=True).start()
        self._bureau: Path | None = None

    # composants -------------------------------------------------------
    def empreinte(self) -> str:
        return hashlib.sha256(EXIGENCES.read_bytes()).hexdigest()[:16]

    def composants_ok(self) -> bool:
        repere = Path(sys.prefix) / "immolev-composants.txt"
        return repere.exists() and repere.read_text().strip() == self.empreinte()

    def installer(self) -> None:
        with self.verrou:
            if self.installation["en_cours"]:
                return
            self.installation = {"en_cours": True, "progression": 2, "ligne": "Démarrage…", "erreur": None}
        threading.Thread(target=self._installer, daemon=True).start()

    def _installer(self) -> None:
        console = Path(sys.executable).with_name("python.exe")
        cmd = [str(console) if console.exists() else sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
               "--progress-bar", "off", "-r", str(EXIGENCES)]
        journal = JOURNAL_DIR / "installation.log"
        etapes = 0
        try:
            with open(journal, "w", encoding="utf-8") as j:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=SYSTEME,
                                     encoding="utf-8", errors="replace", creationflags=systeme.SANS_FENETRE)
                for ligne in p.stdout:
                    j.write(ligne)
                    ligne = ligne.strip()
                    if ligne.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
                        etapes += 1
                        self.installation["progression"] = min(95, 2 + etapes)  # ~120 lignes au total
                        self.installation["ligne"] = ligne[:90]
                code = p.wait()
            if code:
                raise RuntimeError("pip a échoué : voir systeme/journal/installation.log")
            self.installation.update(progression=96, ligne="Téléchargement du modèle vocal (environ 460 Mo)…")
            r = subprocess.run(cmd[:1] + ["-c", "from agent import voix; voix.charger()"], cwd=APP, capture_output=True,
                               text=True, errors="replace", creationflags=systeme.SANS_FENETRE)
            if r.returncode:  # l'agent marche sans : seuls les vocaux attendront
                with open(journal, "a", encoding="utf-8") as j:
                    j.write(r.stdout + r.stderr)
            (Path(sys.prefix) / "immolev-composants.txt").write_text(self.empreinte())
            charger_composants()
            self.installation.update(progression=100, ligne="Composants installés.")
            self.verifier_tout()
        except Exception as e:  # noqa: BLE001 — affiché au gestionnaire
            self.installation["erreur"] = str(e)
        finally:
            self.installation["en_cours"] = False

    # vérifications ----------------------------------------------------
    def verifier_tout(self) -> None:
        if not self.composants_ok():
            return
        threading.Thread(target=self.messagerie.rafraichir_comptes_ms, daemon=True).start()
        self.verifier_ia()
        if (jeton := lire_secret("TELEGRAM_TOKEN")):
            self.verif_bot = verifier_bot(jeton)

    # membres -----------------------------------------------------------
    def noms(self) -> dict:
        f = DONNEES / "membres.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def membres(self) -> list[dict]:
        ids = [m.strip() for m in (lire_secret("TELEGRAM_MEMBRES") or "").split(",") if m.strip()]
        noms = self.noms()
        return [{"id": i, "nom": noms.get(i, "")} for i in ids]

    def changer_membre(self, ident: str, nom: str, ajouter: bool) -> None:
        if not re.fullmatch(r"\d{4,15}", ident):
            raise ValueError("Un identifiant Telegram est un nombre (5 à 15 chiffres).")
        ids = [m["id"] for m in self.membres() if m["id"] != ident]
        noms = self.noms()
        if ajouter:
            ids.append(ident)
            if nom:
                noms[ident] = nom[:60]
        else:
            noms.pop(ident, None)
        ecrire_secret("TELEGRAM_MEMBRES", ",".join(ids))
        (DONNEES / "membres.json").write_text(json.dumps(noms, ensure_ascii=False), encoding="utf-8")
        if ajouter:  # ajout manuel : la personne sort des demandes et des refus
            r = self.registre()
            r.decider(ident, True) if any(d["id"] == ident for d in r.demandes()) else r.oublier_refus(ident)

    def registre(self):
        self._acces()  # met APP dans sys.path
        from agent.membres import Registre
        return Registre(DONNEES, lambda: lire_secret("TELEGRAM_MEMBRES"), lambda v: ecrire_secret("TELEGRAM_MEMBRES", v))

    def demandes(self) -> list[dict]:
        try:
            return self.registre().demandes()
        except Exception:
            return []

    def decider_demande(self, ident: str, accepter: bool) -> None:
        if not self.registre().decider(ident, accepter):
            raise ValueError("Cette demande a déjà été traitée.")

    def chercher_expediteurs(self) -> list[dict]:
        if self.agent()["en_marche"]:
            raise ValueError("Arrêtez l'agent le temps de la recherche (il lit les mêmes messages).")
        jeton = lire_secret("TELEGRAM_TOKEN")
        if not jeton:
            raise ValueError("Enregistrez d'abord le bot Telegram.")
        rep = telegram(jeton, "getUpdates", timeout=0, allowed_updates=["message"])
        if not rep.get("ok"):
            raise ValueError(f"Telegram : {rep.get('description', 'erreur')}")
        vus: dict[str, dict] = {}
        dernier = None
        for u in rep["result"]:
            dernier = u["update_id"]
            m = u.get("message") or {}
            qui = m.get("from") or {}
            if qui.get("is_bot") or "id" not in qui:
                continue
            nom = " ".join(x for x in (qui.get("first_name"), qui.get("last_name")) if x)
            lieu = m.get("chat", {}).get("title") or "message privé au bot"
            vus[str(qui["id"])] = {"id": str(qui["id"]), "nom": nom, "pseudo": qui.get("username"), "lieu": lieu}
        if dernier is not None:  # marque ces messages comme lus : l'agent ne les traitera pas
            telegram(jeton, "getUpdates", offset=dernier + 1, timeout=0)
        deja = {m["id"] for m in self.membres()}
        return [dict(v, autorise=v["id"] in deja) for v in vus.values()]

    # agent -------------------------------------------------------------
    def agent(self) -> dict:
        f = DONNEES / "agent.json"
        info = json.loads(f.read_text()) if f.exists() else {}
        vivant = systeme.processus_vivant(int(info.get("pid", 0)))
        return {"en_marche": vivant, "depuis": info.get("depuis") if vivant else None,
                "arret_inattendu": bool(info) and not vivant and not info.get("arrete")}

    def pret(self) -> list[str]:
        manque = []
        if not self.composants_ok():
            manque.append("installer les composants")
        if not (self.compte() or lire_secret("ANTHROPIC_API_KEY")):
            manque.append("le compte Immolev")
        if not lire_secret("TELEGRAM_TOKEN"):
            manque.append("le bot Telegram")
        if not self.membres():
            manque.append("au moins une personne autorisée")
        if not systeme.chrome():
            manque.append("Google Chrome (à installer sur ce PC)")
        return manque

    def demarrer_agent(self) -> None:
        if self.agent()["en_marche"]:
            return
        if (manque := self.pret()):
            raise ValueError("Il manque : " + ", ".join(manque) + ".")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                   CHROME_PROFIL=str(DONNEES / "chrome-agent"))
        if (DONNEES / "connecteurs.json").exists():
            env["CONNECTEURS"] = str(DONNEES / "connecteurs.json")
        pid = systeme.lancer_detache([systeme.pythonw(), "-m", "agent.telegram"], APP, env,
                                     JOURNAL_DIR / "agent.log")
        (DONNEES / "agent.json").write_text(json.dumps({"pid": pid, "depuis": datetime.now().strftime("%d/%m %H:%M")}))

    # mise à jour ----------------------------------------------------------
    def maj_disponible(self) -> dict | None:
        quand, trouve = self._maj_cache
        if time.time() - quand < 20:
            return trouve
        if self._bureau is None:
            try:
                self._bureau = systeme.dossier_special("Desktop")
            except Exception:
                self._bureau = Path.home() / "Desktop"
        dossiers = [self._bureau, Path.home() / "Downloads", Path.home() / "Téléchargements", SYSTEME.parent.parent]
        trouve = maj.chercher(dossiers, self.version)
        en_ligne = self._maj_en_ligne
        if en_ligne and maj.rang(en_ligne["version"]) > maj.rang(self.version) and \
                (not trouve or maj.rang(en_ligne["version"]) > maj.rang(trouve["version"])):
            trouve = en_ligne
        self._maj_cache = (time.time(), trouve)
        return trouve

    def verifier_ia(self) -> None:
        """Connexion de l'agent à Claude : par la passerelle du site (compte Immolev), sinon par une ancienne clé locale."""
        if (compte := self.compte()):
            self._acces()
            from agent import passerelle
            self.verif_cle = passerelle.ping(compte)
        elif (cle := lire_secret("ANTHROPIC_API_KEY")):
            self.verif_cle = verifier_cle(cle)
        else:
            self.verif_cle = None

    # compte du site Immolev (agent et mises à jour en ligne) ---------------------------
    def compte(self) -> dict | None:
        brut = lire_secret("IMMOLEV_COMPTE")
        return json.loads(brut) if brut else None

    def enregistrer_compte(self, identifiant: str, mot_de_passe: str) -> None:
        compte = {"identifiant": identifiant.strip(), "mot_de_passe": mot_de_passe}
        if not compte["identifiant"] or not mot_de_passe:
            raise ValueError("Indiquez l'identifiant et le mot de passe.")
        try:
            maj.version_en_ligne(compte)
        except PermissionError as e:
            raise ValueError(str(e)) from None
        except OSError as e:
            raise ValueError(f"Site Immolev injoignable : {e}") from None
        ecrire_secret("IMMOLEV_COMPTE", json.dumps(compte))
        self.verifier_ia()
        self.verifier_en_ligne()

    def verifier_en_ligne(self) -> None:
        self._maj_en_ligne = maj.chercher_en_ligne(self.compte(), self.version)
        self._maj_cache = (0, None)

    def _boucle_en_ligne(self) -> None:
        while True:
            try:
                self.verifier_en_ligne()
            except Exception:
                pass
            time.sleep(600)

    def mettre_a_jour(self, contenu: bytes | None, serveur) -> str:
        trouve = self.maj_disponible() or {}
        if contenu is None and trouve.get("url"):
            if not (compte := self.compte()):
                raise ValueError("Enregistrez d'abord le compte Immolev (carte Options).")
            contenu = maj.telecharger(trouve["url"], compte, DONNEES / "maj-telechargee.zip").read_bytes()
        source = contenu if contenu is not None else Path(trouve.get("chemin", ""))
        if not contenu and not source.exists():
            raise ValueError("Aucune nouvelle version trouvée.")
        if maj.version_zip(source) is None:
            raise ValueError("Ce fichier n'est pas un zip Immolev.")
        agent_en_marche = self.agent()["en_marche"]
        self.arreter_agent()
        version = maj.appliquer(source, APP, SYSTEME.parent / "Ouvrir Immolev.vbs")
        args = ["-m", "panneau", "--apres-maj"] + (["--relancer-agent"] if agent_en_marche else [])

        def relancer():  # le nouveau panneau attend 3 s que celui-ci se ferme
            time.sleep(1)
            systeme.lancer_detache([systeme.pythonw(), *args], APP, dict(os.environ), JOURNAL_DIR / "panneau.log")
            serveur.shutdown()
        threading.Thread(target=relancer, daemon=True).start()
        return version

    def redemarrer_si_en_marche(self) -> None:
        if self.agent()["en_marche"]:
            self.arreter_agent()
            time.sleep(2)
            self.demarrer_agent()

    # accès aux sites -----------------------------------------------------
    def _acces(self):
        if str(APP) not in sys.path:
            sys.path.insert(0, str(APP))
        from agent import acces
        return acces

    def dicter(self, audio: bytes) -> str:
        """Transcrit une dictée du panneau dans un Python à part (le modèle n'encombre pas le panneau)."""
        if not self.composants_ok():
            raise ValueError("Installez d'abord les composants.")
        if not audio:
            raise ValueError("Aucun son reçu.")
        fichier = DONNEES / "dictee.webm"
        fichier.write_bytes(audio)
        try:
            python = Path(sys.executable).with_name("python.exe")
            r = subprocess.run([str(python if python.exists() else sys.executable), "-m", "agent.voix", str(fichier)], cwd=APP,
                               capture_output=True, timeout=600, creationflags=systeme.SANS_FENETRE)
        finally:
            fichier.unlink(missing_ok=True)
        if r.returncode:
            with open(JOURNAL_DIR / "panneau.log", "a", encoding="utf-8") as log:
                log.write(f"dictée : {r.stderr.decode('utf-8', 'replace')[-2000:]}\n")
            raise ValueError("Transcription impossible (détails dans systeme/journal/panneau.log).")
        return r.stdout.decode("utf-8", "replace").strip()

    def regles(self) -> dict:
        try:
            self._acces()
            from agent import regles
            texte = regles.lire()
            return {"texte": texte or regles.MODELE, "vide": not texte}
        except Exception:
            return {"texte": "", "vide": True}

    def fiche(self) -> dict:
        try:
            self._acces()
            from agent import fiche
            rep = fiche.lire()
            return {"questions": [{"id": i, "theme": t, "question": q, "exemple": ex, "reponse": rep.get(i, "")}
                                  for i, t, q, ex in fiche.QUESTIONS],
                    "procedures": [{"nom": n, "etapes": e} for n, e in fiche.procedures().items()],
                    "reglementation": fiche.connaissances()}
        except Exception:
            return {"questions": [], "procedures": [], "reglementation": ""}

    def acces(self) -> list[dict]:
        try:
            return self._acces().lister()
        except Exception:
            return []

    def arreter_agent(self) -> None:
        f = DONNEES / "agent.json"
        if f.exists():
            info = json.loads(f.read_text())
            if systeme.processus_vivant(int(info.get("pid", 0))):
                systeme.arreter_processus(int(info["pid"]))
            info["arrete"] = True
            f.write_text(json.dumps(info))

    # compte Google de l'agent --------------------------------------------
    def google_agent(self) -> dict:
        try:
            info = json.loads((DONNEES / "google-agent.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if info.get("fait") and not info.get("ouvert") and "adresses" not in info:  # connexion faite avant l'affichage de l'adresse
            info["adresses"] = comptes_chrome(DONNEES / "chrome-agent")
        return info

    def ouvrir_google_agent(self, adresse: str = "") -> None:
        """Arrête l'agent le temps de la connexion (le profil Chrome ne sert qu'à une fenêtre), puis ouvre Google."""
        relancer = self.agent()["en_marche"] or bool(self.google_agent().get("relancer"))
        if self.agent()["en_marche"]:
            self.arreter_agent()
            time.sleep(2)
        url = "https://accounts.google.com/"
        if "@" in adresse:
            from urllib.parse import quote
            url = "https://accounts.google.com/AddSession?login_hint=" + quote(adresse)
        systeme.ouvrir_chrome_profil(url, DONNEES / "chrome-agent")
        DONNEES.mkdir(parents=True, exist_ok=True)
        (DONNEES / "google-agent.json").write_text(json.dumps(
            {"fait": bool(self.google_agent().get("fait")), "ouvert": True, "relancer": relancer}), encoding="utf-8")

    def terminer_google_agent(self) -> None:
        if systeme.profil_utilise(DONNEES / "chrome-agent"):
            raise ValueError("Fermez d'abord la fenêtre Chrome de connexion Google, puis recliquez sur « J'ai terminé ».")
        relancer = bool(self.google_agent().get("relancer"))
        (DONNEES / "google-agent.json").write_text(json.dumps({"fait": True, "ouvert": False, "relancer": False,
            "adresses": comptes_chrome(DONNEES / "chrome-agent")}), encoding="utf-8")
        if relancer and not self.pret():
            self.demarrer_agent()

    # options -----------------------------------------------------------
    def lien_demarrage(self) -> Path:
        return systeme.dossier_special("Startup") / "Immolev agent.lnk"

    def options(self) -> dict:
        try:
            return {"demarrage": self.lien_demarrage().exists()}
        except Exception:
            return {"demarrage": False}

    def raccourci_bureau(self) -> None:
        systeme.creer_raccourci(systeme.dossier_special("Desktop") / "Immolev.lnk", systeme.pythonw(),
                                "-m panneau", APP, ICONE)

    def demarrage_windows(self, actif: bool) -> None:
        lien = self.lien_demarrage()
        if actif:
            systeme.creer_raccourci(lien, systeme.pythonw(), "-m panneau --agent", APP, ICONE)
        elif lien.exists():
            lien.unlink()

    # intelligence de l'agent : modèle et plafond par demande (lus par agent/orchestrateur.py) ---------
    def ia(self) -> dict:
        def lire(nom, defaut):
            try:
                return json.loads((DONNEES / nom).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return defaut
        reg = {"modele": "standard", "plafond": 1.0, **lire("reglages-ia.json", {})}
        return {**reg, "couts": lire("cout-demandes.json", [])[-8:][::-1]}

    def regler_ia(self, modele: str, plafond) -> None:
        if modele not in ("economique", "standard", "puissant"):
            raise ValueError("Modèle inconnu.")
        try:
            plafond = round(float(str(plafond).replace(",", ".")), 2)
        except ValueError:
            raise ValueError("Plafond invalide : un montant en euros, ex. 0,50.") from None
        if not 0.05 <= plafond <= 50:
            raise ValueError("Plafond entre 0,05 € et 50 €.")
        DONNEES.mkdir(parents=True, exist_ok=True)
        (DONNEES / "reglages-ia.json").write_text(json.dumps({"modele": modele, "plafond": plafond}), encoding="utf-8")

    def vue(self) -> dict:
        cle, jeton, compte = lire_secret("ANTHROPIC_API_KEY"), lire_secret("TELEGRAM_TOKEN"), self.compte()
        return {
            "composants": {"ok": self.composants_ok(), **self.installation},
            "chrome": bool(systeme.chrome()),
            "cle": {"enregistree": bool(compte or cle), "verif": self.verif_cle},
            "bot": {"enregistre": bool(jeton), "apercu": apercu(jeton, 6), "verif": self.verif_bot},
            "membres": self.membres() if self.composants_ok() else [],
            "demandes": self.demandes() if self.composants_ok() else [],
            "messagerie": self.messagerie.vue(),
            "acces": self.acces(),
            "regles": self.regles(),
            "fiche": self.fiche(),
            "version": self.version,
            "compte": (self.compte() or {}).get("identifiant"),
            "maj": self.maj_disponible(),
            "agent": self.agent(),
            "google_agent": self.google_agent(),
            "options": self.options(),
            "visage": {"choix": visage.lire(DONNEES), "liste": visage.liste(),
                       "perso": (DONNEES / "visage-perso.jpg").exists()},
            "ia": self.ia(),
        }


# ---------------------------------------------------------------- serveur HTTP local

def creer_serveur(etat: Etat, jeton: str, port: int = 0) -> ThreadingHTTPServer:
    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *a):  # pas de journal des requêtes
            pass

        def _envoyer(self, code: int, corps: bytes, type_: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def _json(self, code: int, donnees) -> None:
            self._envoyer(code, json.dumps(donnees, ensure_ascii=False).encode())

        def _autorise(self) -> bool:
            hote_ok = self.headers.get("Host") == f"127.0.0.1:{self.server.server_address[1]}"
            return hote_ok and secrets.compare_digest(self.headers.get("X-Immolev", ""), jeton)

        def do_GET(self):
            if self.path.split("?")[0] == "/":
                return self._envoyer(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/logo":
                return self._envoyer(200, Path(__file__).with_name("logo.svg").read_bytes(), "image/svg+xml")
            if self.path == "/icone":
                return self._envoyer(200, ICONE.read_bytes(), "image/x-icon") if ICONE.exists() else self._json(404, {})
            if self.path.startswith("/avatar/"):  # images publiques du panneau (pas de secret)
                img = visage.image(self.path.split("/")[-1].split("?")[0], DONNEES)
                return self._envoyer(200, img, "image/jpeg") if img else self._json(404, {})
            if self.path == "/api/vivant":
                return self._json(200, {"ok": True})
            if not self._autorise():
                return self._json(403, {"erreur": "refusé"})
            etat.dernier_ping = time.time()
            if self.path == "/api/etat":
                return self._json(200, etat.vue())
            if self.path == "/api/journal":
                f = JOURNAL_DIR / "agent.log"
                lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()[-80:] if f.exists() else []
                return self._json(200, {"lignes": lignes})
            self._json(404, {"erreur": "inconnu"})

        def do_POST(self):
            if not self._autorise():
                return self._json(403, {"erreur": "refusé"})
            etat.dernier_ping = time.time()
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corps = json.loads(self.rfile.read(n) or b"{}") if n else {}
                rep = self._action(self.path, corps)
                self._json(200, rep or {"ok": True})
            except ValueError as e:
                self._json(400, {"erreur": str(e)})
            except Exception as e:  # noqa: BLE001
                self._json(500, {"erreur": f"{type(e).__name__} : {e}"})

        def _action(self, chemin: str, c: dict):
            if chemin == "/api/installer":
                etat.installer()
            elif chemin == "/api/google-agent/ouvrir":
                etat.ouvrir_google_agent(str(c.get("adresse", "")))
            elif chemin == "/api/google-agent/terminer":
                etat.terminer_google_agent()
            elif chemin == "/api/bot":
                jeton_bot = propre(c.get("valeur"))
                verif = verifier_bot(jeton_bot)
                if verif["ok"] is False:
                    raise ValueError(verif["message"])
                ecrire_secret("TELEGRAM_TOKEN", jeton_bot)
                etat.verif_bot = verif
                choix = visage.lire(DONNEES)
                if choix:  # visage choisi avant le bot : on le pose maintenant
                    threading.Thread(target=visage.choisir, args=(DONNEES, choix["id"], choix["nom"], jeton_bot),
                                     daemon=True).start()
            elif chemin == "/api/ia":
                etat.regler_ia(str(c.get("modele", "")), c.get("plafond", ""))
            elif chemin == "/api/visage/importer":
                visage.importer(DONNEES, base64.b64decode(str(c.get("image", "")).split(",")[-1]))
            elif chemin == "/api/visage":
                rep = visage.choisir(DONNEES, str(c.get("id", "")), str(c.get("nom", "")), lire_secret("TELEGRAM_TOKEN"))
                return rep  # l'agent relit son prénom à chaque demande
            elif chemin == "/api/membres/chercher":
                return {"expediteurs": etat.chercher_expediteurs()}
            elif chemin == "/api/membres/demande":
                etat.decider_demande(str(c.get("id", "")), bool(c.get("accepter")))
            elif chemin == "/api/membres":
                etat.changer_membre(str(c.get("id", "")).strip(), str(c.get("nom", "")).strip(), bool(c.get("ajouter")))
            elif chemin == "/api/agent/demarrer":
                etat.demarrer_agent()
            elif chemin == "/api/agent/arreter":
                etat.arreter_agent()
            elif chemin == "/api/bureau":
                etat.raccourci_bureau()
            elif chemin == "/api/demarrage":
                etat.demarrage_windows(bool(c.get("actif")))
            elif chemin == "/api/acces":
                etat._acces().enregistrer(str(c.get("nom", "")), str(c.get("url", "")), str(c.get("identifiant", "")),
                                          str(c.get("mot_de_passe", "")), c.get("id") or None,
                                          "gmail" if c.get("mode") == "gmail" else "mdp", str(c.get("gmail", "")))
            elif chemin == "/api/acces/supprimer":
                etat._acces().supprimer(str(c.get("id", "")))
            elif chemin == "/api/gmail/client":
                etat.messagerie.importer_client_google(str(c.get("contenu", "")))
            elif chemin == "/api/mail/ajouter":
                return {"adresse": etat.messagerie.ajouter_mail(str(c.get("adresse", "")), str(c.get("code", "")),
                                                                str(c.get("imap", "")), str(c.get("smtp", "")))}
            elif chemin == "/api/mail/retirer":
                etat.messagerie.retirer_mail(str(c.get("adresse", "")))
            elif chemin == "/api/gmail/annuler":
                etat.messagerie.annuler_gmail()
            elif chemin == "/api/gmail/ajouter":
                etat.messagerie.ajouter_gmail()
            elif chemin == "/api/gmail/retirer":
                etat.messagerie.retirer_gmail(str(c.get("adresse", "")))
            elif chemin == "/api/outlook/node":
                etat.messagerie.installer_node()
            elif chemin == "/api/outlook/ajouter":
                etat.messagerie.ajouter_ms()
            elif chemin == "/api/outlook/retirer":
                etat.messagerie.retirer_ms(str(c.get("id", "")))
            elif chemin == "/api/dicter":
                return {"texte": etat.dicter(base64.b64decode(str(c.get("audio", ""))))}
            elif chemin == "/api/regles":
                etat._acces()
                from agent import regles
                regles.ecrire(str(c.get("texte", "")))
            elif chemin == "/api/fiche":
                etat._acces()
                from agent import fiche
                fiche.ecrire(dict(c.get("reponses") or {}))
            elif chemin == "/api/procedure/supprimer":
                etat._acces()
                from agent import fiche
                fiche.supprimer_procedure(str(c.get("nom", "")))
            elif chemin == "/api/maj":
                contenu = base64.b64decode(c["contenu"]) if c.get("contenu") else None
                return {"version": etat.mettre_a_jour(contenu, self.server)}
            elif chemin == "/api/quitter":  # avant une mise à jour : libère tous les fichiers du dossier
                etat.arreter_agent()
                threading.Thread(target=lambda: (time.sleep(1), self.server.shutdown()), daemon=True).start()
            elif chemin == "/api/compte":
                etat.enregistrer_compte(str(c.get("identifiant", "")), str(c.get("mot_de_passe", "")))
            elif chemin == "/api/actualiser":  # revérifie clé, bot, boîtes mail et cherche une mise à jour
                etat.verifier_en_ligne()
                threading.Thread(target=etat.verifier_tout, daemon=True).start()
                return {"maj": etat.maj_disponible()}
            elif chemin == "/api/ping":
                pass
            else:
                raise ValueError("Action inconnue.")

    return ThreadingHTTPServer(("127.0.0.1", port), Gestion)


def deja_ouvert() -> str | None:
    f = DONNEES / "panneau.json"
    if not f.exists():
        return None
    info = json.loads(f.read_text())
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/api/vivant", timeout=2)
        return info["url"]
    except OSError:
        return None


def main(argv: list[str]) -> None:
    etat = Etat()
    if "--agent" in argv:  # démarrage de Windows : l'agent seul, sans fenêtre
        if not etat.pret():
            etat.demarrer_agent()
        return
    if "--apres-maj" in argv:  # laisse l'ancien panneau se fermer
        time.sleep(3)
        if not etat.composants_ok():
            etat.installer()
        elif "--relancer-agent" in argv:
            try:
                etat.demarrer_agent()
            except ValueError:
                pass
    if (url := deja_ouvert()):
        systeme.ouvrir_fenetre(url, DONNEES / "fenetre")
        return
    jeton = secrets.token_urlsafe(24)
    serveur = creer_serveur(etat, jeton)
    port = serveur.server_address[1]
    url = f"http://127.0.0.1:{port}/?t={jeton}"
    (DONNEES / "panneau.json").write_text(json.dumps({"port": port, "url": url}))
    threading.Thread(target=etat.verifier_tout, daemon=True).start()

    def veille():  # fenêtre fermée depuis 2 min et rien en cours : on s'arrête
        while True:
            time.sleep(15)
            occupe = etat.installation["en_cours"] or etat.messagerie.gmail_connexion["en_cours"] or etat.messagerie.ms_connexion["en_cours"]
            if time.time() - etat.dernier_ping > 120 and not occupe:
                serveur.shutdown()
                return
    threading.Thread(target=veille, daemon=True).start()
    if "--sans-fenetre" not in argv:
        systeme.ouvrir_fenetre(url, DONNEES / "fenetre")
    serveur.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
