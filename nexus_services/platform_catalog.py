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
    {"category": "sports", "name": "1xBet", "status": "ANDROID_APP_OFFICIAL_DOWNLOAD", "source": "Application Android; téléchargement depuis la page mobile officielle de 1xBet.", "connection_mode": "Télécharger l’application Android", "url": "https://1xbet.com/en/mobile"},
    {"category": "sports", "name": "BetWinner", "status": "ANDROID_APP_OFFICIAL_DOWNLOAD", "source": "Application Android; téléchargement depuis le site officiel de BetWinner.", "connection_mode": "Télécharger l’application Android", "url": "https://betwinner.com/en/mobile"},
    {"category": "sports", "name": "MelBet", "status": "ANDROID_APP_OFFICIAL_DOWNLOAD", "source": "Application Android; centre d’applications officiel MelBet.", "connection_mode": "Télécharger l’application Android", "url": "https://guidebook.melbet.com/app/"},
    {"category": "sports", "name": "Betway Ghana", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle publiée par Sports Betting Group Ghana Limited.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.betway.gh"},
    {"category": "sports", "name": "Betway Afrique du Sud", "status": "ANDROID_APP_OFFICIAL_DOWNLOAD", "source": "Application Android; téléchargement depuis la page officielle Betway Afrique du Sud.", "connection_mode": "Télécharger l’application Android", "url": "https://www.betway.co.za/Betway-App"},
    {"category": "sports", "name": "DraftKings", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.draftkings.sportsbook"},
    {"category": "sports", "name": "FanDuel", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.fanduel.sportsbook"},
    {"category": "sports", "name": "BetMGM", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.playmgm.nj.sports"},
    {"category": "sports", "name": "bet365", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; l’offre dépend du pays et de la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.bet365SportsNJ.Bet365_ApplicationNJ"},
    {"category": "sports", "name": "Caesars Sportsbook", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.williamhill.us.nj.sports"},
    {"category": "sports", "name": "Fanatics Sports & Casino", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.betfanatics.sportsbook.android"},
    {"category": "sports", "name": "BetRivers", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle; disponibilité limitée selon la juridiction.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.rush.ri"},
    {"category": "sports", "name": "Betfair Sportsbook", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle Betfair; offre régionale.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.betfair.sportsbook"},
    {"category": "sports", "name": "Paddy Power", "status": "ANDROID_APP_GOOGLE_PLAY", "source": "Application Android officielle Paddy Power; offre régionale.", "connection_mode": "Installer depuis Google Play", "url": "https://play.google.com/store/apps/details?id=com.paddypower.sportsbook.u.inhouse"},
    {"category": "payments", "name": "Stripe / PayPal / Revolut", "status": "LEGACY_CODE_REFERENCE_NOT_CONNECTED", "source": "Références dans d’anciens points d’entrée; non configurées dans Render.", "connection_mode": "Aucune opération de paiement automatisée"},
)


def get_platform_catalog(category: str | None = None) -> list[dict[str, Any]]:
    """Return a copy of the fixed inventory, optionally filtered by category."""
    entries = PLATFORMS if category is None else tuple(
        item for item in PLATFORMS if item["category"] == category
    )
    return deepcopy(list(entries))
