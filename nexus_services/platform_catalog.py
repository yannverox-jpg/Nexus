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
    {"category": "sports", "name": "1xBet", "status": "REQUESTED_NOT_CONNECTED", "source": "Opérateur de paris sportifs", "connection_mode": "Ouvrir la plateforme", "url": "https://1xbet.com/"},
    {"category": "sports", "name": "Google Search", "status": "REQUESTED_NOT_CONNECTED", "source": "Recherche d’événements, d’équipes et de cotes publiques", "connection_mode": "Ouvrir la recherche", "url": "https://www.google.com/search?q=football+matchs+du+jour+cotes"},
    {"category": "sports", "name": "YouTube", "status": "REQUESTED_NOT_CONNECTED", "source": "Vidéos et analyses sportives publiques", "connection_mode": "Ouvrir YouTube", "url": "https://www.youtube.com/results?search_query=analyse+football"},
    {"category": "sports", "name": "Telegram", "status": "REQUESTED_NOT_CONNECTED", "source": "Sources sportives publiques", "connection_mode": "Ouvrir Telegram Web", "url": "https://web.telegram.org/"},
    {"category": "sports", "name": "Sites sportifs (à définir)", "status": "TARGET_UNSPECIFIED", "source": "Aucun site ni liste de sources validées disponible.", "connection_mode": "Non configuré"},
    {"category": "payments", "name": "Stripe / PayPal / Revolut", "status": "LEGACY_CODE_REFERENCE_NOT_CONNECTED", "source": "Références dans d’anciens points d’entrée; non configurées dans Render.", "connection_mode": "Aucune opération de paiement automatisée"},
)


def get_platform_catalog(category: str | None = None) -> list[dict[str, Any]]:
    """Return a copy of the fixed inventory, optionally filtered by category."""
    entries = PLATFORMS if category is None else tuple(
        item for item in PLATFORMS if item["category"] == category
    )
    return deepcopy(list(entries))
