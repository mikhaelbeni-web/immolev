"""Range les secrets dans le coffre de Windows (Gestionnaire d'identification), jamais dans un fichier.

Lancer une fois : python configurer.py   (ou via installer.bat)
"""
import getpass
import json
import subprocess
import sys
from pathlib import Path

from agent import coffre as keyring

SERVICE = "immolev"


def cle_valide(cle):
    """Teste la clé auprès d'Anthropic (liste des modèles : gratuit, ne consomme rien)."""
    import anthropic
    try:
        anthropic.Anthropic(api_key=cle).models.list(limit=1)
    except anthropic.AuthenticationError:
        print("  -> refusé par Anthropic : ce n'est pas une clé API valide. "
              "Crée-la sur console.anthropic.com > API Keys > Create Key.")
        return False
    except Exception as e:
        print(f"  !! Test impossible ({type(e).__name__}) : clé enregistrée sans vérification.")
        return True
    print("  -> clé acceptée par Anthropic.")
    return True


print("Les valeurs tapées ne s'affichent pas et ne sont écrites dans aucun fichier.")
print("Pour coller : CLIC DROIT dans la fenêtre (Ctrl+V peut ne rien faire), puis Entrée.\n")
for nom, invite, cache in (
    ("ANTHROPIC_API_KEY", "Clé API Claude (console.anthropic.com)", True),
    ("TELEGRAM_TOKEN", "Jeton du bot Telegram (@BotFather)", True),
    ("TELEGRAM_MEMBRES", "Identifiants Telegram autorisés, séparés par des virgules", False),
):
    actuel = keyring.get_password(SERVICE, nom)
    while True:
        valeur = (getpass.getpass if cache else input)(f"{invite}{' [Entrée = garder l actuel]' if actuel else ''} : ").strip()
        if not valeur:
            if actuel:
                break
            print("  -> rien reçu. Colle avec un CLIC DROIT dans la fenêtre, puis Entrée.")
            continue
        if len(valeur) > 300 or any(c.isspace() for c in valeur.replace(", ", ",")):
            # Le presse-papiers contenait autre chose (texte copié pour le fil, etc.)
            print(f"  -> refusé : {len(valeur)} caractères reçus, ce n'est pas une clé. "
                  "Recopie uniquement la clé, puis recolle.")
            continue
        if cache:
            # Rien ne s'affiche pendant la saisie : on confirme sans révéler la valeur
            print(f"  -> reçu : {valeur[:13]}…{valeur[-4:]} ({len(valeur)} caractères)")
            if nom == "ANTHROPIC_API_KEY" and not cle_valide(valeur):
                continue
        keyring.set_password(SERVICE, nom, valeur)
        break
print("\nSecrets enregistrés dans le coffre Windows (service « immolev »).")

# Messagerie : au choix du gestionnaire
modele = json.loads(Path("connecteurs.exemple.json").read_text(encoding="utf-8"))
choix = input("\nMessagerie du gestionnaire : 1 = Gmail, 2 = Outlook / Hotmail, 3 = Microsoft 365 pro, Entrée = aucune : ").strip()
config = {}
if choix == "1":
    config["gmail"] = modele["gmail"]
    print("Connexion Gmail : Chrome va s'ouvrir, accepte l'accès à la boîte du gestionnaire.")
    subprocess.run([sys.executable, "-m", "connecteurs.gmail_mcp", "--connexion"], check=False)
elif choix in ("2", "3"):
    config["outlook"] = modele["outlook"]
    if choix == "3":
        config["outlook"]["args"].append("--org-mode")
        config["outlook"]["env"].pop("MS365_MCP_TENANT_ID", None)
    print("Connexion Microsoft : suis l'adresse et le code affichés ci-dessous.")
    subprocess.run(["npx", "-y", "@softeria/ms-365-mcp-server", "--login"] + (["--org-mode"] if choix == "3" else []), check=False, shell=sys.platform == "win32")
if config:
    Path("connecteurs.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print("connecteurs.json écrit.")
