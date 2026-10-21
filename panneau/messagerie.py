"""Boîtes mail du gestionnaire : plusieurs Gmail et plusieurs Outlook / Hotmail, ajoutées depuis le panneau.

- Gmail : notre connecteur (connecteurs/gmail_mcp.py), un client OAuth Google importé une fois.
- Outlook / Hotmail : @softeria/ms-365-mcp-server (Node.js), qui gère lui-même plusieurs comptes ;
  connexion par code à saisir sur microsoft.com/devicelogin.
Le panneau écrit connecteurs.json dans le dossier de données ; l'agent le lit au démarrage.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

from . import systeme

PAQUET_MS = "@softeria/ms-365-mcp-server@0.168.0"
LECTURE_MS = ["list-accounts", "list-mail-messages", "list-mail-folders", "list-mail-folder-messages", "get-mail-message",
              "list-mail-attachments", "get-mail-attachment-content", "list-calendar-events", "get-calendar-event"]


NODE = "https://nodejs.org/dist"


def _lire_url(url: str, timeout: int = 300) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Immolev"}), timeout=timeout) as r:
        return r.read()


def installer_node_portable(dossier: Path, lire=_lire_url) -> Path:
    """Node.js LTS officiel (zip Windows 64 bits) vérifié par SHASUMS256.txt de nodejs.org, extrait dans dossier."""
    version = next(v["version"] for v in json.loads(lire(f"{NODE}/index.json", 60)) if v.get("lts"))
    nom = f"node-{version}-win-x64"
    sommes = lire(f"{NODE}/{version}/SHASUMS256.txt", 60).decode()
    attendu = next((l.split()[0] for l in sommes.splitlines() if l.strip().endswith(f"{nom}.zip")), None)
    if not attendu:
        raise RuntimeError(f"empreinte de {nom}.zip absente de nodejs.org")
    contenu = lire(f"{NODE}/{version}/{nom}.zip")
    if hashlib.sha256(contenu).hexdigest() != attendu:
        raise RuntimeError("le fichier Node.js téléchargé ne correspond pas à son empreinte officielle")
    temp = dossier.with_name(dossier.name + "-temp")
    shutil.rmtree(temp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        z.extractall(temp)
    shutil.rmtree(dossier, ignore_errors=True)
    (temp / nom).replace(dossier)
    shutil.rmtree(temp, ignore_errors=True)
    return dossier


class Messagerie:
    def __init__(self, donnees: Path, app: Path, journal: Path):
        self.donnees, self.app, self.journal = donnees, app, journal
        self.fichier = donnees / "messagerie.json"
        self.gmail_connexion = {"en_cours": False, "erreur": None}
        self._essai_google, self._proc_google = 0, None
        self.ms_connexion = {"en_cours": False, "code": None, "url": None, "erreur": None}
        self.node_installation = {"en_cours": False, "erreur": None}
        self.ms_comptes: list[dict] | None = None
        self.apres_changement = lambda: None  # le panneau y branche le redémarrage de l'agent

    # état ----------------------------------------------------------------
    def _lire(self) -> dict:
        d = json.loads(self.fichier.read_text(encoding="utf-8")) if self.fichier.exists() else {}
        d.setdefault("gmail", []); d.setdefault("outlook", False); d.setdefault("mail", [])
        return d

    def _ecrire(self, d: dict) -> None:
        self.fichier.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self._ecrire_connecteurs(d)

    def client_google(self) -> Path | None:
        for f in (self.donnees / "google-client.json", self.app / "google-client.json"):
            if f.exists():
                return f
        return None

    def npx(self) -> str | None:
        trouve = shutil.which("npx")
        if trouve:
            return trouve
        for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA"), str(self.donnees)):
            if base and (p := Path(base) / "nodejs" / "npx.cmd").exists():
                return str(p)
        return None

    def _env_node(self) -> dict:
        """PATH avec le dossier de npx en tête : le Node.js portable d'Immolev n'est pas dans le PATH de Windows."""
        env = dict(os.environ)
        if (npx := self.npx()) and os.path.isabs(npx):
            env["PATH"] = os.path.dirname(npx) + os.pathsep + env.get("PATH", "")
        return env

    def vue(self) -> dict:
        d = self._lire()
        return {
            "mail": d["mail"],
            "gmail": {"client": bool(self.client_google()), "comptes": d["gmail"], "connexion": self.gmail_connexion},
            "outlook": {"node": bool(self.npx()), "actif": d["outlook"], "comptes": self.ms_comptes,
                        "connexion": self.ms_connexion, "installation_node": self.node_installation},
        }

    def _ecrire_connecteurs(self, d: dict) -> None:
        config = {}
        if d["gmail"]:
            config["gmail"] = {"commande": "python", "args": ["-m", "connecteurs.gmail_mcp", "--comptes", ",".join(d["gmail"])]}
        if d["mail"]:
            config["mail"] = {"commande": "python", "args": ["-m", "connecteurs.imap_mcp", "--comptes", ",".join(d["mail"])]}
        if d["outlook"] and (npx := self.npx()):
            config["outlook"] = {"commande": npx, "args": ["-y", PAQUET_MS], "lecture": LECTURE_MS}
        f = self.donnees / "connecteurs.json"
        if config:
            f.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
        elif f.exists():
            f.unlink()

    # Mail par code (IMAP/SMTP) ---------------------------------------------
    def ajouter_mail(self, adresse: str, code: str, imap: str = "", smtp: str = "") -> str:
        if str(self.app) not in sys.path:
            sys.path.insert(0, str(self.app))
        from connecteurs.imap_mcp import enregistrer
        boite = enregistrer(adresse, code, imap.strip(), smtp.strip())  # teste la connexion avant d'enregistrer
        d = self._lire()
        if boite.adresse not in d["mail"]:
            d["mail"].append(boite.adresse)
        self._ecrire(d)
        self.apres_changement()
        return boite.adresse

    def retirer_mail(self, adresse: str) -> None:
        d = self._lire()
        d["mail"] = [a for a in d["mail"] if a != adresse]
        self._ecrire(d)
        try:
            from agent import coffre as keyring
            keyring.delete_password("immolev", f"MAIL:{adresse}")
        except Exception:
            pass
        self.apres_changement()

    # Gmail -----------------------------------------------------------------
    def importer_client_google(self, contenu: str) -> None:
        try:
            d = json.loads(contenu)
        except ValueError:
            raise ValueError("Ce fichier n'est pas un fichier JSON de Google.") from None
        if "installed" not in d:
            raise ValueError("Il faut un identifiant OAuth de type « Application de bureau » (le fichier contient « installed »).")
        for dossier in (self.donnees, self.app):  # dans app/ : suit le dossier Immolev copié sur un autre PC
            try:
                (dossier / "google-client.json").write_text(json.dumps(d), encoding="utf-8")
            except OSError:
                pass

    def ajouter_gmail(self) -> None:
        """Lance (ou relance) la connexion Google. Un nouveau clic abandonne la tentative précédente."""
        if not self.client_google():
            raise ValueError("Importez d'abord le fichier client Google.")
        self.annuler_gmail()
        self._essai_google += 1
        self.gmail_connexion = {"en_cours": True, "erreur": None}
        threading.Thread(target=self._ajouter_gmail, args=(self._essai_google,), daemon=True).start()

    def annuler_gmail(self) -> None:
        self._essai_google += 1  # la tentative en cours ne touchera plus l'état affiché
        proc, self._proc_google = self._proc_google, None
        if proc and proc.poll() is None:
            proc.kill()
        self.gmail_connexion = {"en_cours": False, "erreur": None}

    def _ajouter_gmail(self, essai: int) -> None:
        try:
            adresse = self._connexion_google()
            if essai != self._essai_google:
                return
            d = self._lire()
            if adresse not in d["gmail"]:
                d["gmail"].append(adresse)
            self._ecrire(d)
            self.apres_changement()
        except Exception as e:  # noqa: BLE001 — affiché dans le panneau
            if essai == self._essai_google:
                self.gmail_connexion["erreur"] = f"Connexion Gmail interrompue : {e}"
        finally:
            if essai == self._essai_google:
                self.gmail_connexion["en_cours"] = False

    def _connexion_google(self) -> str:
        """Connexion Google dans un Python neuf : les composants installés après l'ouverture du panneau y sont
        chargés normalement (cause de « No module named 'pywintypes' »)."""
        exe = Path(sys.executable)
        python = exe.with_name("python.exe") if exe.with_name("python.exe").exists() else exe
        resultat = self.donnees / "connexion-google.json"
        resultat.unlink(missing_ok=True)
        with open(self.journal / "gmail.log", "a", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen([str(python), "-m", "connecteurs.gmail_mcp", "--connexion", str(self.client_google()), str(resultat)],
                                    cwd=self.app, stdout=log, stderr=log, creationflags=systeme.SANS_FENETRE)
            self._proc_google = proc
            try:
                proc.wait(timeout=300)  # au-delà de 5 min, la page Google a été abandonnée
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError("délai dépassé. Recliquez sur Continuer avec Google.") from None
        if not resultat.exists():
            raise RuntimeError("connexion abandonnée. Recliquez sur Continuer avec Google.")
        sortie = json.loads(resultat.read_text(encoding="utf-8"))
        resultat.unlink(missing_ok=True)
        if "erreur" in sortie:
            with open(self.journal / "gmail.log", "a", encoding="utf-8") as log:
                log.write(sortie.get("trace", ""))
            raise RuntimeError(sortie["erreur"])
        return sortie["adresse"]

    def retirer_gmail(self, adresse: str) -> None:
        d = self._lire()
        d["gmail"] = [a for a in d["gmail"] if a != adresse]
        self._ecrire(d)
        try:
            from agent import coffre as keyring
            keyring.delete_password("immolev", f"GMAIL_JETON:{adresse}")
        except Exception:
            pass
        self.apres_changement()

    # Outlook / Hotmail --------------------------------------------------------
    def _ms(self, *args: str, timeout: int = 180) -> dict:
        npx = self.npx()
        if not npx:
            raise ValueError("Installez d'abord le composant Microsoft.")
        r = subprocess.run([npx, "-y", PAQUET_MS, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=systeme.SANS_FENETRE, cwd=self.donnees,
                           env=self._env_node())
        for ligne in reversed(r.stdout.splitlines()):
            if ligne.strip().startswith("{"):
                return json.loads(ligne)
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:] or "réponse vide")

    def rafraichir_comptes_ms(self) -> None:
        if not self._lire()["outlook"] or not self.npx():
            self.ms_comptes = []
            return
        try:
            self.ms_comptes = [{"id": c["id"], "adresse": c.get("username") or c.get("name") or "?"}
                               for c in self._ms("--list-accounts").get("accounts", [])]
        except Exception as e:  # noqa: BLE001
            self.ms_connexion["erreur"] = f"Lecture des comptes Microsoft impossible : {e}"

    def installer_node(self) -> None:
        if self.node_installation["en_cours"]:
            return
        self.node_installation = {"en_cours": True, "erreur": None}

        def tache():
            try:
                if shutil.which("winget"):
                    subprocess.run(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--silent",
                                    "--accept-package-agreements", "--accept-source-agreements"],
                                   capture_output=True, text=True, errors="replace", creationflags=systeme.SANS_FENETRE, timeout=900)
                if not self.npx():  # pas de winget (Windows sans « App Installer ») ou échec : Node.js portable, sans droits admin
                    installer_node_portable(self.donnees / "nodejs")
                if not self.npx():
                    raise RuntimeError("Node.js introuvable après installation")
            except Exception as e:  # noqa: BLE001
                self.node_installation["erreur"] = f"Installation de Node.js impossible : {e}. Installez-le depuis nodejs.org."
            finally:
                self.node_installation["en_cours"] = False
        threading.Thread(target=tache, daemon=True).start()

    def ajouter_ms(self) -> None:
        npx = self.npx()
        if not npx:
            raise ValueError("Installez d'abord le composant Microsoft.")
        if self.ms_connexion["en_cours"]:
            return
        self.ms_connexion = {"en_cours": True, "code": None, "url": None, "erreur": None}
        threading.Thread(target=self._ajouter_ms, args=(npx,), daemon=True).start()

    def _ajouter_ms(self, npx: str) -> None:
        try:
            p = subprocess.Popen([npx, "-y", PAQUET_MS, "--login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", creationflags=systeme.SANS_FENETRE, cwd=self.donnees,
                                 env=self._env_node())
            sortie = []
            for ligne in p.stdout:
                sortie.append(ligne)
                if (m := re.search(r"https://[^\s'\"]+", ligne)) and not self.ms_connexion["url"]:
                    self.ms_connexion["url"] = m.group(0).rstrip(".")
                if (m := re.search(r"code\s+([A-Z0-9]{6,12})\b", ligne)) and not self.ms_connexion["code"]:
                    self.ms_connexion["code"] = m.group(1)
                    webbrowser.open(self.ms_connexion["url"] or "https://microsoft.com/devicelogin")
            if p.wait(timeout=900):
                raise RuntimeError("".join(sortie).strip()[-300:])
            d = self._lire()
            d["outlook"] = True
            self._ecrire(d)
            self.rafraichir_comptes_ms()
            self.apres_changement()
        except Exception as e:  # noqa: BLE001
            self.ms_connexion["erreur"] = f"Connexion Microsoft interrompue : {e}"
        finally:
            self.ms_connexion.update(en_cours=False, code=None)

    def retirer_ms(self, ident: str) -> None:
        self._ms("--remove-account", ident)
        self.rafraichir_comptes_ms()
        if not self.ms_comptes:
            d = self._lire()
            d["outlook"] = False
            self._ecrire(d)
        self.apres_changement()
