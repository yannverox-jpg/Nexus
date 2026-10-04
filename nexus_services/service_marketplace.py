import json
from typing import Dict, Any, Optional

class ServiceCatalogRegistry:
    """
    Registre centralisé des micro-services exécutables disponibles pour Nexus.
    Gère les endpoints, les coûts unitaires et les critères de validation des livrables.
    """
    def __init__(self, catalog_path: Optional[str] = None):
        self.services: Dict[str, Dict[str, Any]] = {}
        if catalog_path:
            self.load_from_json(catalog_path)
        else:
            self._load_default_catalog()

    def _load_default_catalog(self):
        self.services = {
            "CONTRACT_VERIFIER": {
                "endpoint": "https://api.nexus.internal/v1/verify",
                "cost_per_call_usdc": 0.5,
                "method": "POST",
                "timeout_sec": 5.0,
                "requires_auth": True
            },
            "EXECUTION_PROVIDER": {
                "endpoint": "https://api.nexus.internal/v1/execute",
                "cost_per_call_usdc": 2.0,
                "method": "POST",
                "timeout_sec": 30.0,
                "requires_auth": True
            },
            "DATA_PARSER": {
                "endpoint": "https://api.nexus.internal/v1/parse",
                "cost_per_call_usdc": 0.1,
                "method": "POST",
                "timeout_sec": 3.0,
                "requires_auth": False
            }
        }

    def register_service(self, name: str, endpoint: str, cost_usdc: float, method: str = "POST"):
        self.services[name] = {
            "endpoint": endpoint,
            "cost_per_call_usdc": cost_usdc,
            "method": method,
            "timeout_sec": 10.0,
            "requires_auth": True
        }

    def get_service(self, name: str) -> Optional[Dict[str, Any]]:
        return self.services.get(name)

    def load_from_json(self, path: str):
        with open(path, "r") as f:
            self.services = json.load(f)
