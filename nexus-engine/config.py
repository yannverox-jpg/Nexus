import os

class Config:
    # ROI Minimal pour accepter une tâche (Ex: 1.5 = 150% de rentabilité)
    MIN_ROI_RATIO = float(os.getenv("MIN_ROI_RATIO", "1.5"))

    # Nombre maximal de sous-agents simultanés
    MAX_CONCURRENT_WORKERS = int(os.getenv("MAX_CONCURRENT_WORKERS", "50"))

    # Nom de l'environnement
    ENV = os.getenv("ENV", "production")

    # Solana Configuration
    SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    NEXUS_PRIVATE_KEY = os.getenv("NEXUS_PRIVATE_KEY", "")
