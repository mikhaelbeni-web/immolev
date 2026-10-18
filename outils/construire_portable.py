"""Fabrique Immolev.zip : dossier portable Windows (Python embarqué + code + panneau).

    python outils/construire_portable.py <cpython-3.12-windows-install_only_stripped.tar.gz> <dist/Immolev-v{n}.zip>

Le Python vient de python-build-standalone (astral-sh), vérifié par SHA256 avant l'appel.
Les dépendances lourdes ne sont pas incluses : le panneau les installe au premier lancement.
Le coffre des secrets (keyring et ses dépendances, en Python pur) est embarqué depuis outils/roues.
"""
from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CODE = ["agent", "document", "connecteurs", "panneau", "requirements-agent.txt", "connecteurs.exemple.json"]
INUTILE_PY = ["tcl", "Lib/tkinter", "Lib/idlelib", "Lib/turtledemo", "Lib/ensurepip", "Lib/test", "include", "libs",
              "DLLs/_tkinter.pyd", "DLLs/tcl86t.dll", "DLLs/tk86t.dll"]

LANCEUR = r'''' Ouvre le panneau Immolev (aucune fenetre noire).
Set fso = CreateObject("Scripting.FileSystemObject")
racine = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = racine & "\systeme\app"
sh.Run """" & racine & "\systeme\python\pythonw.exe"" -m panneau", 0, False
'''

LISEZ_MOI = """IMMOLEV - agent du gestionnaire

1. Double-cliquez sur « Ouvrir Immolev ».
2. Suivez le panneau : composants, clé API Claude, bot Telegram, personnes autorisées.
3. Cliquez sur « Démarrer l'agent », puis connectez-vous à vos logiciels et à votre banque dans le Chrome qui s'ouvre.

Prérequis : Windows 10 ou 11, Google Chrome, Internet.
Aucune clé n'est enregistrée dans ce dossier : elles restent dans le coffre Windows de chaque PC.
"""


def construire(archive_python: Path, sortie: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "Immolev"
        systeme = base / "systeme"
        systeme.mkdir(parents=True)
        with tarfile.open(archive_python) as t:
            t.extractall(systeme, filter="data")  # crée systeme/python
        for chemin in INUTILE_PY:
            p = systeme / "python" / chemin
            shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
        paquets = systeme / "python" / "Lib" / "site-packages"
        paquets.mkdir(parents=True, exist_ok=True)
        roues = sorted((RACINE / "outils" / "roues").glob("*.whl"))
        if not roues:
            raise SystemExit("outils/roues est vide : le coffre des secrets ne serait pas embarqué.")
        for roue in roues:
            with zipfile.ZipFile(roue) as z:
                z.extractall(paquets)
        app = systeme / "app"
        for nom in CODE:
            src = RACINE / nom
            if src.is_dir():
                shutil.copytree(src, app / nom, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                app.mkdir(exist_ok=True)
                shutil.copy2(src, app / nom)
        # numéro simple (1, 2, 3…) : +1 à chaque construction, gardé dans outils/NUMERO
        numero_f = Path(__file__).with_name("NUMERO")
        numero = int(numero_f.read_text().strip()) + 1 if numero_f.exists() else 1
        numero_f.write_text(str(numero))
        (app / "VERSION").write_text(str(numero), encoding="utf-8")
        sortie = sortie.with_name(sortie.name.replace("{n}", str(numero)))  # ex. dist/Immolev-v{n}.zip → Immolev-v6.zip
        (base / "Ouvrir Immolev.vbs").write_text(LANCEUR.replace("\n", "\r\n"), encoding="ascii")
        (base / "LISEZ-MOI.txt").write_text(LISEZ_MOI.replace("\n", "\r\n"), encoding="utf-8-sig")
        sortie.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for f in sorted(base.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(base.parent))
    print(f"{sortie} : {sortie.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    construire(Path(sys.argv[1]), Path(sys.argv[2]))
