"""Connecteurs MCP d'Immolev."""

# HTTPS vérifié avec les certificats de Windows (antivirus, proxy d'entreprise qui inspecte le trafic), jamais désactivé.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # truststore absent (développement) : vérification Python habituelle
    pass
