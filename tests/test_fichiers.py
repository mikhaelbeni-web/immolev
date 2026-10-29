import io
import json
from pathlib import Path

from agent import fichiers


def _xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Manquantes"
    ws.append(["Fournisseur", "Montant"])
    ws.append(["LEROY MERLIN", 5779.8])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _pdf_texte() -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    page = w.add_blank_page(300, 300)
    police = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                               NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): police})})
    flux = DecodedStreamObject()
    flux.set_data(b"BT /F1 12 Tf 20 200 Td (Facture TEMU 22,25 EUR du 12 octobre 2026 pour la societe) Tj ET")
    page[NameObject("/Contents")] = w._add_object(flux)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def test_lire_formats():
    t = fichiers.lire_octets("FACTURES MANQUANTES.xlsx", _xlsx())
    assert "Manquantes" in t and "LEROY MERLIN;5779.8" in t
    assert "TEMU 22,25" in fichiers.lire_octets("f.pdf", _pdf_texte(), transcrire=lambda o, m: "NON")
    assert fichiers.lire_octets("scan.pdf", b"%PDF-1.4 vide", transcrire=lambda o, m: "texte scanne") == "texte scanne"
    assert fichiers.lire_octets("photo.jpg", b"\xff\xd8", transcrire=lambda o, m: m) == "image/jpeg"
    assert "ancien format" in fichiers.lire_octets("vieux.xls", b"x")


class FauxConnecteurs:
    sessions = {"outlook": object()}

    def __init__(self, dossier: Path):
        self.appels = []

    def appeler(self, serveur, outil, args):
        self.appels.append((outil, args))
        if outil == "list-mail-attachments":
            return json.dumps({"value": [{"id": "PJ1", "name": "FACTURES MANQUANTES du 12102026.xlsx"}, {"id": "PJ2", "name": "TEMU22.25.pdf"}]})
        if outil == "download-bytes-to-file":
            Path(args["outputPath"]).write_bytes(_xlsx())
            return json.dumps({"path": args["outputPath"]})
        if outil == "list-drives":
            return json.dumps({"value": [{"id": "X", "name": "ODCMetadataArchive"}, {"id": "B81", "name": "OneDrive"}]})
        if outil == "upload-file-content":
            return json.dumps({"id": "n1", "webUrl": "https://onedrive.live.com/x"})
        raise AssertionError(outil)


def test_piece_jointe_outlook_puis_onedrive(tmp_path, monkeypatch):
    monkeypatch.setattr(fichiers, "dossier_donnees", lambda: tmp_path)
    c = FauxConnecteurs(tmp_path)
    o = fichiers.outils_fichiers(c)
    r = o["lire_piece_jointe"].executer(mail_id="AAMk=", nom="manquantes")
    assert "LEROY MERLIN" in r and "Fichier enregistré : AAMk/FACTURES MANQUANTES du 12102026.xlsx" in r
    assert c.appels[1][1]["target"] == "/me/messages/AAMk=/attachments/PJ1/$value"
    assert "LEROY" in o["lire_fichier"].executer(nom="FACTURES MANQUANTES du 12102026.xlsx")
    r = o["deposer_onedrive"].executer(nom="AAMk/FACTURES MANQUANTES du 12102026.xlsx", sous_dossier="AMEX 2026")
    assert "Immolev/AMEX 2026/FACTURES MANQUANTES du 12102026.xlsx" in r and "onedrive.live.com" in r
    assert c.appels[-1][1]["driveId"] == "B81" and c.appels[-1][1]["driveItemId"].startswith("root:/Immolev/AMEX 2026/")
    try:
        o["lire_fichier"].executer(nom="../../etc/passwd")
        assert False
    except ValueError:
        pass


def test_sans_connecteur(tmp_path, monkeypatch):
    monkeypatch.setattr(fichiers, "dossier_donnees", lambda: tmp_path)
    assert set(fichiers.outils_fichiers(None)) == {"lire_fichier"}
