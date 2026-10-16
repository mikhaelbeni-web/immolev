"""Transcription de la voix (vocaux Telegram, dictée des règles dans le panneau), sur le PC du magasin.

faster-whisper, modèle « large-v3-turbo » (le Whisper d'OpenAI, version rapide) en int8 sur le processeur :
qualité proche de la dictée de ChatGPT, l'audio ne quitte pas le PC. Le modèle (~1,6 Go) est téléchargé
par le panneau à l'installation des composants ; s'il manque, repli sur « small » (~460 Mo).
Un vocabulaire d'optique est donné au modèle pour qu'il écrive juste les termes du métier.

    python -m agent.voix fichier_audio     # écrit le texte sur la sortie (utilisé par le panneau)
"""
from __future__ import annotations

import io
import logging
import os
import sys
import threading

from .acces import dossier_donnees

MODELE = os.environ.get("WHISPER_MODELE", "large-v3-turbo")
SECOURS = "small"
VOCABULAIRE = ("Magasin d'optique. Ordonnance, ophtalmologiste, orthoptiste, sphère, cylindre, axe, addition, "
               "prisme, écart pupillaire, verres progressifs, unifocaux, monture, lentilles, tiers payant, mutuelle, "
               "prise en charge, devis, facture, MyEasyOptic, Almerys, Viamedis, iSanté, Kalixia, Itelis, Santéclair, "
               "carte Vitale, Sécurité sociale, rendez-vous.")
_modele = None
_verrou = threading.Lock()


def dossier_modeles() -> str:
    return str(dossier_donnees() / "whisper")


def charger():
    global _modele
    with _verrou:
        if _modele is None:
            from faster_whisper import WhisperModel
            try:
                _modele = WhisperModel(MODELE, device="cpu", compute_type="int8", download_root=dossier_modeles())
            except Exception:
                logging.exception("modèle vocal %s indisponible, repli sur %s", MODELE, SECOURS)
                _modele = WhisperModel(SECOURS, device="cpu", compute_type="int8", download_root=dossier_modeles())
    return _modele


def decoder(audio: bytes):
    """Audio (ogg, webm, mp3…) → échantillons 16 kHz mono. Fait ici plutôt que par faster-whisper,
    dont le décodeur appelle une option que les versions récentes de PyAV ont retirée."""
    import av
    import numpy as np
    morceaux = []
    with av.open(io.BytesIO(audio), mode="r") as conteneur:
        reechantillonneur = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for trame in conteneur.decode(audio=0):
            morceaux += [t.to_ndarray().reshape(-1) for t in reechantillonneur.resample(trame)]
        morceaux += [t.to_ndarray().reshape(-1) for t in reechantillonneur.resample(None)]
    return (np.concatenate(morceaux).astype(np.float32) / 32768.0) if morceaux else np.zeros(0, dtype=np.float32)


def transcrire(audio: bytes) -> str:
    echantillons = decoder(audio)
    if len(echantillons) < 1600:  # moins de 0,1 s
        return ""
    segments, _ = charger().transcribe(echantillons, language="fr", vad_filter=True, beam_size=5,
                                       initial_prompt=VOCABULAIRE, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as f:
        texte = transcrire(f.read())
    sys.stdout.buffer.write(texte.encode("utf-8"))
