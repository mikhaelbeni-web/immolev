"""Coffre des secrets : le coffre Windows (keyring) en priorité, sinon un fichier chiffré par Windows (DPAPI).

Même interface que keyring (get_password / set_password / delete_password). Si le module keyring manque ou si
le coffre système répond par une erreur, les secrets sont gardés dans %LOCALAPPDATA%\\Immolev\\coffre.json,
chiffrés avec le compte Windows de l'utilisateur : illisibles depuis un autre PC ou un autre compte.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Callable


def _dpapi(chiffrer: bool) -> Callable[[bytes], bytes]:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def appel(donnees: bytes) -> bytes:
        entree = Blob(len(donnees), ctypes.cast(ctypes.create_string_buffer(donnees, len(donnees)),
                                                 ctypes.POINTER(ctypes.c_char)))
        sortie = Blob()
        f = ctypes.windll.crypt32.CryptProtectData if chiffrer else ctypes.windll.crypt32.CryptUnprotectData
        if not f(ctypes.byref(entree), None, None, None, None, 0, ctypes.byref(sortie)):
            raise OSError("Le coffre Windows a refusé l'opération.")
        try:
            return ctypes.string_at(sortie.pbData, sortie.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(sortie.pbData)

    return appel


class Coffre:
    def __init__(self, fichier: Path | None = None, chiffrer: Callable[[bytes], bytes] | None = None,
                 dechiffrer: Callable[[bytes], bytes] | None = None, utiliser_keyring: bool = True):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".immolev")
        self.fichier = fichier or base / "Immolev" / "coffre.json"
        self._chiffrer = chiffrer
        self._dechiffrer = dechiffrer
        self.utiliser_keyring = utiliser_keyring

    # -- coffre système
    def _keyring(self):
        if not self.utiliser_keyring:
            return None
        try:
            import importlib
            importlib.invalidate_caches()
            import keyring
            return keyring
        except Exception:
            return None

    # -- fichier chiffré
    def _c(self, donnees: bytes) -> bytes:
        return (self._chiffrer or _dpapi(True))(donnees)

    def _d(self, donnees: bytes) -> bytes:
        return (self._dechiffrer or _dpapi(False))(donnees)

    def _lire(self) -> dict:
        try:
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _ecrire(self, contenu: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(contenu), encoding="utf-8")
        os.replace(tmp, self.fichier)

    @staticmethod
    def _cle(service: str, nom: str) -> str:
        return f"{service}\n{nom}"

    # -- interface
    def get_password(self, service: str, nom: str) -> str | None:
        k = self._keyring()
        if k is not None:
            try:
                valeur = k.get_password(service, nom)
                if valeur is not None:
                    return valeur
            except Exception:
                pass
        brut = self._lire().get(self._cle(service, nom))
        if brut is None:
            return None
        try:
            return self._d(base64.b64decode(brut)).decode("utf-8")
        except Exception:
            return None

    def set_password(self, service: str, nom: str, valeur: str) -> None:
        k = self._keyring()
        if k is not None:
            try:
                k.set_password(service, nom, valeur)
                return
            except Exception:
                pass
        contenu = self._lire()
        contenu[self._cle(service, nom)] = base64.b64encode(self._c(valeur.encode("utf-8"))).decode("ascii")
        self._ecrire(contenu)

    def delete_password(self, service: str, nom: str) -> None:
        k = self._keyring()
        if k is not None:
            try:
                k.delete_password(service, nom)
            except Exception:
                pass
        contenu = self._lire()
        if contenu.pop(self._cle(service, nom), None) is not None:
            self._ecrire(contenu)


_defaut = Coffre()
get_password = _defaut.get_password
set_password = _defaut.set_password
delete_password = _defaut.delete_password
