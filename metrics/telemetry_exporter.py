from prometheus_client import start_http_server, Gauge, Counter
import time
import random

# Définition des métriques industrielles de Nexus
NEXUS_GPU_VRAM_USAGE = Gauge('nexus_gpu_vram_usage_bytes', 'Utilisation VRAM du cluster GPU', ['gpu_id'])
NEXUS_ACTIVE_LEASES = Gauge('nexus_active_leases', 'Nombre de baux de tâches actifs en simultané')
NEXUS_DLQ_ERRORS = Counter('nexus_dlq_errors_total', 'Nombre total de messages rejetés dans la DLQ')
NEXUS_CIRCUIT_STATE = Gauge('nexus_circuit_breaker_status', 'État du Circuit Breaker (0=Closed, 1=Half-Open, 2=Open)')

def export_nexus_telemetry(port: int = 9090):
    """Exose les métriques en continu pour le scraping Prometheus."""
    start_http_server(port)
    print(f"[TELEMETRY] Serveur de métriques Prometheus démarré sur le port {port}.")

def update_telemetry_snapshot():
    for i in range(4): # Exemple sur 4 cartes graphiques principales du cluster
        NEXUS_GPU_VRAM_USAGE.labels(gpu_id=f"GPU-{i}").set(random.randint(12000000000, 24000000000))

    NEXUS_ACTIVE_LEASES.set(random.randint(10, 50))
    NEXUS_CIRCUIT_STATE.set(0) # 0 = CLOSED (Normal)

if __name__ == "__main__":
    export_nexus_telemetry(9090)
    while True:
        update_telemetry_snapshot()
        time.sleep(2)
