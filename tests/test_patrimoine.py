from agent import patrimoine

TEXTE = """# Patrimoine
Source : OneDrive « plan immeuble ».

## 81 rue de Sèvres, 75006
| Lot | Carrez |
|---|---|
| 2G | 48,2 m² |
Plan : plan immeuble/81 rue de sevres/ARCHI/81 rue de Sèvres-Plans_VF.pdf

## 93 rue du Commerce, 75015
| 4D | 30 m² |
"""


def test_consulter(tmp_path):
    assert "absent" in patrimoine.consulter(tmp_path, "sevres")
    (tmp_path / patrimoine.FICHIER).write_text(TEXTE, encoding="utf-8")
    r = patrimoine.consulter(tmp_path, "Sèvres 2G")
    assert "48,2" in r and "Commerce" not in r
    assert "4D" in patrimoine.consulter(tmp_path, "commerce")
    liste = patrimoine.consulter(tmp_path, "")
    assert "81 rue de Sèvres" in liste and "93 rue du Commerce" in liste
    assert "Immeubles connus" in patrimoine.consulter(tmp_path, "washington")


def test_pieces_jointes_limitees_au_dossier_plans(tmp_path):
    import email
    import email.policy
    import base64
    import pytest
    from connecteurs.gmail_mcp import _brut, fichiers_joints
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "93-commerce.pdf").write_bytes(b"%PDF-1.4 plan")
    (tmp_path / "secret.json").write_text("{}")
    assert fichiers_joints("", plans) == []
    joints = fichiers_joints("93-commerce.pdf", plans)
    m = email.message_from_bytes(base64.urlsafe_b64decode(_brut("a@b.fr", "Appartement", "Bonjour", joints)), policy=email.policy.default)
    assert [p.get_filename() for p in m.iter_attachments()] == ["93-commerce.pdf"]
    for interdit in ("../secret.json", "absent.pdf", "/etc/passwd"):
        with pytest.raises(ValueError):
            fichiers_joints(interdit, plans)
