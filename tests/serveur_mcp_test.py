"""Faux serveur de messagerie MCP pour les tests : une lecture, une écriture."""
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

serveur = MCPServer("messagerie-test")
ENVOYES: list[str] = []


@serveur.tool(annotations=ToolAnnotations(read_only_hint=True))
def chercher_mails(requete: str) -> str:
    """Cherche des mails."""
    return f"2 mails pour « {requete} » : accord PEC Almerys n°123 ; rejet Viamedis motif droits fermés"


@serveur.tool()
def envoyer_mail(destinataire: str, sujet: str) -> str:
    """Envoie un mail."""
    return f"Mail « {sujet} » envoyé à {destinataire}"


if __name__ == "__main__":
    serveur.run()
