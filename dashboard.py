"""Nexus OS dashboard entry point backed by the private operational API."""

from nexus_services.embedded_api import ensure_operational_api
from nexus_services.operational_dashboard_view import render_dashboard


ensure_operational_api()
render_dashboard()