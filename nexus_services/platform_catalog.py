"""Fixed inventory of requested platform targets and connector readiness."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PLATFORMS: tuple[dict[str, Any], ...] = (
    {"category": "microservices", "name": "Plateformes de micro-tâches (à définir)", "status": "TARGET_UNSPECIFIED", "source": "Aucune plateforme nommée dans le dépôt ou configurée.", "connection_mode": "Non configuré"},
    {"category": "ecommerce", "name": "Amazon", "status": "REQUESTED_NOT_CONNECTED", "source": "Cible demandée; aucun connecteur de compte détecté.", "connection_mode": "Connexion manuelle uniquement"},
    {"category": "ecommerce", "name": "Shopify", "status": "REQUESTED_NOT_CONNECTED", "source": "Cible demandée; aucun connecteur de compte détecté.", "connection_mode": "Connexion manuelle uniquement"},
    {"category": "ecommerce", "name": "Alibaba", "status": "REQUESTED_NOT_CONNECTED", "source": "Cible demandée; aucun connecteur de compte détecté.", "connection_mode": "Connexion manuelle uniquement"},
    {"category": "ecommerce", "name": "eBay", "status": "REQUESTED_NOT_CONNECTED", "source": "Cible demandée; aucun connecteur de compte détecté.", "connection_mode": "Connexion manuelle uniquement"},
    {"category": "trading", "name": "MetaTrader 5", "status": "OPTIONAL_CODE_REFERENCE_NOT_CONNECTED", "source": "Référence optionnelle dans l’API existante; aucun compte/connecteur prêt.", "connection_mode": "Aucune connexion; observation/simulation seulement"},
    {"category": "sports", "name": "1xBet", "status": "REQUESTED_NOT_CONNECTED", "source": "Cible demandée; aucun connecteur de compte détecté.", "connection_mode": "Consultation manuelle; aucun pari automatisé"},
    {"category": "sports", "name": "Google Search", "status": "REQUESTED_NOT_CONNECTED", "source": "Source de recherche demandée; aucune collecte configurée.", "connection_mode": "Recherche manuelle; pas de scraping automatisé"},
    {"category": "sports", "name": "YouTube Live", "status": "REQUESTED_NOT_CONNECTED", "source": "Source vidéo demandée; aucune analyse de flux configurée.", "connection_mode": "Consultation manuelle"},
    {"category": "sports", "name": "Telegram (sources publiques)", "status": "REQUESTED_NOT_CONNECTED", "source": "Source de groupes demandée; aucun connecteur configuré.", "connection_mode": "Consultation manuelle; aucune exploitation de compte"},
    {"category": "sports", "name": "Sites sportifs (à définir)", "status": "TARGET_UNSPECIFIED", "source": "Aucun site ni liste de sources validées disponible.", "connection_mode": "Non configuré"},
    {"category": "payments", "name": "Stripe / PayPal / Revolut", "status": "LEGACY_CODE_REFERENCE_NOT_CONNECTED", "source": "Références dans d’anciens points d’entrée; non configurées dans Render.", "connection_mode": "Aucune opération de paiement automatisée"},
)


def get_platform_catalog(category: str | None = None) -> list[dict[str, Any]]:
    """Return a copy of the fixed inventory, optionally filtered by category."""
    entries = PLATFORMS if category is None else tuple(
        item for item in PLATFORMS if item["category"] == category
    )
    return deepcopy(list(entries))
