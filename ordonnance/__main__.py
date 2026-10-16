"""Usage : python -m ordonnance photo.jpg"""
import json
import sys
from dataclasses import asdict

from .extract import extraire_fichier
from .validation import transposer, valider

if len(sys.argv) != 2:
    sys.exit(__doc__)
ordo = extraire_fichier(sys.argv[1])
sortie = {
    "ordonnance": ordo.model_dump(mode="json"),
    "cylindre_negatif": {"od": transposer(ordo.od).model_dump(), "og": transposer(ordo.og).model_dump()},
    "alertes": [asdict(a) for a in valider(ordo)],
}
print(json.dumps(sortie, ensure_ascii=False, indent=2))
sys.exit(1 if any(a["niveau"] == "bloquant" for a in sortie["alertes"]) else 0)
