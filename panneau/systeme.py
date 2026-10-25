"""Ce qui dépend de Windows : processus, raccourcis, Chrome. Replis simples ailleurs (tests)."""
from __future__ import annotations

import base64
import os
import shutil
import signal
import subprocess
import time
import sys
import webbrowser
from pathlib import Path

WINDOWS = sys.platform == "win32"
SANS_FENETRE = 0x08000000 if WINDOWS else 0  # CREATE_NO_WINDOW


def pythonw() -> str:
    """pythonw.exe (aucune fenêtre noire) à côté de l'interpréteur courant."""
    candidat = Path(sys.executable).with_name("pythonw.exe")
    return str(candidat) if candidat.exists() else sys.executable


def processus_vivant(pid: int) -> bool:
    if pid <= 0:
        return False
    if WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # processus terminé mais pas encore récupéré par son parent
        return os.waitpid(pid, os.WNOHANG) == (0, 0)
    except ChildProcessError:
        return True


def arreter_processus(pid: int) -> None:
    """Arrête le processus et ses enfants (pilote Playwright, Chrome de l'agent)."""
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=SANS_FENETRE)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass


def lancer_detache(commande: list[str], dossier: Path, env: dict, journal: Path) -> int:
    sortie = open(journal, "w", encoding="utf-8")
    if WINDOWS:
        drapeaux = 0x00000008 | 0x00000200 | SANS_FENETRE  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        p = subprocess.Popen(commande, cwd=dossier, env=env, stdout=sortie, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=drapeaux)
    else:
        p = subprocess.Popen(commande, cwd=dossier, env=env, stdout=sortie, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    sortie.close()
    return p.pid


def chrome() -> str | None:
    if not WINDOWS:
        return shutil.which("google-chrome") or shutil.which("chromium")
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base and (p := Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe").exists():
            return str(p)
    return None


def ouvrir_chrome_profil(url: str, profil: Path) -> None:
    """Chrome ordinaire (sans pilotage, donc Google accepte la connexion) sur le profil dédié à l'agent."""
    navigateur = chrome()
    if not navigateur:
        raise RuntimeError("Google Chrome n'est pas installé sur ce PC.")
    profil.mkdir(parents=True, exist_ok=True)
    # --disable-background-mode : fermer la fenêtre ferme vraiment Chrome (sinon il reste en arrière-plan et garde le profil)
    subprocess.Popen([navigateur, f"--user-data-dir={profil}", "--no-first-run", "--no-default-browser-check",
                      "--disable-background-mode", url], creationflags=SANS_FENETRE)


def profil_utilise(profil: Path) -> bool:
    """Vrai si une fenêtre Chrome utilise encore ce profil (Chrome garde son fichier « lockfile » verrouillé sous Windows)."""
    verrou = profil / "lockfile"
    if not WINDOWS or not verrou.exists():
        return False
    try:
        with open(verrou, "ab"):
            return False
    except OSError:
        return True


def fermer_chrome_profil(profil: Path, attente: float = 8.0) -> bool:
    """Ferme les Chrome restés ouverts sur ce profil : d'abord poliment (Chrome enregistre ses cookies), puis de force.
    Vrai si le profil est libre à la fin."""
    if not profil_utilise(profil):
        return True
    if WINDOWS:
        motif = _ps(f"*{profil}*")
        lister = f"(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object {{ $_.CommandLine -like {motif} }}).ProcessId"
        for force in (False, True):
            try:
                pids = [p for p in _powershell(lister).split() if p.isdigit()]
            except Exception:  # noqa: BLE001
                pids = []
            for pid in pids:
                subprocess.run(["taskkill", "/PID", pid, "/T", *(["/F"] if force else [])], capture_output=True, creationflags=SANS_FENETRE)
            fin = time.time() + attente
            while time.time() < fin:
                if not profil_utilise(profil):
                    return True
                time.sleep(0.5)
    return not profil_utilise(profil)


def edge() -> str | None:
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and (p := Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe").exists():
            return str(p)
    return None


def ouvrir_fenetre(url: str, profil: Path) -> None:
    """Ouvre le panneau comme une application (sans barre d'adresse), sinon dans le navigateur."""
    navigateur = chrome() or edge() if WINDOWS else None
    if navigateur:
        subprocess.Popen([navigateur, f"--app={url}", f"--user-data-dir={profil}", "--window-size=1000,900",
                          "--no-first-run", "--no-default-browser-check"], creationflags=SANS_FENETRE)
    else:
        webbrowser.open(url)


def _powershell(script: str) -> str:
    code = base64.b64encode(script.encode("utf-16-le")).decode()
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", code],
                       capture_output=True, text=True, creationflags=SANS_FENETRE, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "PowerShell a échoué")
    return r.stdout.strip()


def _ps(chaine: str) -> str:
    return "'" + chaine.replace("'", "''") + "'"


def dossier_special(nom: str) -> Path:
    """Desktop ou Startup, y compris un Bureau déplacé dans OneDrive."""
    if not WINDOWS:
        return Path.home() / nom
    return Path(_powershell(f"[Environment]::GetFolderPath({_ps(nom)})"))


def creer_raccourci(lien: Path, cible: str, arguments: str, dossier: Path, icone: Path | None) -> None:
    if not WINDOWS:
        lien.parent.mkdir(parents=True, exist_ok=True)
        lien.write_text(f"{cible} {arguments}\n", encoding="utf-8")
        return
    script = (f"$r = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps(str(lien))});"
              f"$r.TargetPath = {_ps(cible)}; $r.Arguments = {_ps(arguments)};"
              f"$r.WorkingDirectory = {_ps(str(dossier))};"
              + (f"$r.IconLocation = {_ps(str(icone))};" if icone and icone.exists() else "")
              + "$r.Save()")
    _powershell(script)
