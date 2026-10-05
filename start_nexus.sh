#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo "🛡️ Démarrage du Command Center Nexus OS..."
streamlit run dashboard.py --server.port=8501 --server.address=0.0.0.0
