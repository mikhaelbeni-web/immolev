"""Usage : python -m document photo.jpg"""
import json
import sys
from dataclasses import asdict

from .extract import extraire_fichier
from .validation import valider

if len(sys.argv) != 2:
    sys.exit(__doc__)
doc = extraire_fichier(sys.argv[1])
sortie = {"document": doc.model_dump(mode="json"), "alertes": [asdict(a) for a in valider(doc)]}
print(json.dumps(sortie, ensure_ascii=False, indent=2))
sys.exit(1 if any(a["niveau"] == "bloquant" for a in sortie["alertes"]) else 0)
