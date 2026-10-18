"""Place le dernier zip construit dans l'espace protégé du site (site/telecharger) avec version.json.

    python outils/publier.py dist/Immolev-v7.zip
Ensuite : git commit + push ; Vercel publie, et les panneaux des utilisateurs proposent la mise à jour.
"""
import json
import shutil
import sys
import zipfile
from pathlib import Path

source = Path(sys.argv[1])
version = zipfile.ZipFile(source).read("Immolev/systeme/app/VERSION").decode().strip()
cible = Path(__file__).resolve().parent.parent / "site" / "telecharger"
for ancien in cible.glob("Immolev*.zip"):
    ancien.unlink()
shutil.copy2(source, cible / source.name)
(cible / "version.json").write_text(json.dumps({"version": version, "fichier": source.name}), encoding="utf-8")
print(f"Version {version} publiée dans {cible}")
