"""Streamlit command center backed only by the canonical operational API."""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st


def _get_json(base_url: str, path: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Operational API unavailable for {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Operational API returned an invalid response for {path}")
    return data


def _post_json(base_url: str, path: str, payload: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Browser operation unavailable: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Browser operation returned an invalid response")
    return data


def _delete_json(base_url: str, path: str) -> Dict[str, Any]:
    request = Request(f"{base_url.rstrip('/')}{path}", method="DELETE")
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Connection operation unavailable: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Connection operation returned an invalid response")
    return data


def _handle_oauth_callback(base_url: str) -> None:
    """Complete a provider redirect and immediately remove callback data from the URL."""
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    error = st.query_params.get("error")
    if error:
        st.error("Le fournisseur a refusé ou annulé la connexion.")
        st.query_params.clear()
    elif code and state:
        try:
            result = _post_json(base_url, "/api/v1/connections/oauth/callback", {
                "code": str(code), "state": str(state),
            })
        except RuntimeError as exc:
            st.error(f"La connexion OAuth n’a pas abouti : {exc}")
        else:
            st.success(f"Compte connecté : {result.get('provider_id')}.")
        finally:
            st.query_params.clear()


def _render_managed_connections(base_url: str, integrations: Dict[str, Any]) -> None:
    st.subheader("Connexions de comptes")
    st.caption(
        "Connecte les comptes via OAuth officiel. Nexus chiffre les jetons et peut les renouveler "
        "quand le fournisseur l’autorise. Les agents peuvent travailler automatiquement dans "
        "les limites définies par les autorisations et règles du compte. Aucun mot de passe, "
        "cookie, numéro complet de carte ni CVV n’est enregistré ici."
    )
    connection_data = integrations.get("connections", {})
    providers = connection_data.get("providers", [])
    if not providers:
        st.info("Les comptes sont gérés depuis leurs plateformes respectives.")
        return
    for provider in providers:
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.markdown(f"**{provider.get('name', provider.get('provider_id'))}**")
            scopes = ", ".join(provider.get("scopes", []))
            if scopes:
                left.caption(f"Autorisations demandées : {scopes}")
            if provider.get("status") in ("AUTHORIZED", "RECONNECT_REQUIRED"):
                if right.button("Déconnecter", key=f"disconnect_{provider['provider_id']}"):
                    try:
                        _delete_json(base_url, f"/api/v1/connections/{provider['provider_id']}")
                    except RuntimeError as exc:
                        st.error(str(exc))
                    else:
                        st.success("Compte déconnecté.")
                        st.rerun()
            else:
                remember = right.checkbox(
                    "Se souvenir de moi", value=False,
                    disabled=not provider.get("remember_me_available", False),
                    key=f"remember_{provider['provider_id']}",
                )
                if right.button(
                    "Connecter le compte", key=f"connect_{provider['provider_id']}",
                    disabled=not provider.get("configured", False),
                ):
                    try:
                        result = _post_json(
                            base_url,
                            f"/api/v1/connections/{provider['provider_id']}/oauth/start",
                            {"remember_me": remember},
                        )
                    except RuntimeError as exc:
                        st.error(str(exc))
                    else:
                        st.link_button("Autoriser chez le fournisseur", result["authorization_url"])
            if not provider.get("configured"):
                left.caption("Configuration OAuth incomplète côté serveur.")


def _inject_nexus_theme() -> None:
    st.markdown("""
    <style>
      :root { --navy:#071B2E; --navy2:#0C2941; --black:#050B14; --green:#36D399;
              --orange:#FF9F43; --white:#F3F7FA; --red:#FF5D68; --muted:#A9BAC8; }
      .stApp { background: radial-gradient(ellipse at 12% 0%, #103653 0, #071B2E 42%, #050B14 100%); color:var(--white); }
      [data-testid="stHeader"] { background:rgba(5,11,20,.75); }
      [data-testid="stSidebar"] { background:linear-gradient(180deg,#061522,#091D2D); border-right:1px solid #21435a; }
      [data-testid="stMetric"] { background:linear-gradient(145deg,rgba(15,46,69,.96),rgba(6,20,33,.96));
          border:1px solid #25465b; border-radius:16px; padding:16px 18px; box-shadow:0 12px 30px #0003; }
      [data-testid="stMetricLabel"] p { color:#b6c8d5 !important; }
      [data-testid="stMetricValue"] { color:#36D399 !important; }
      .nexus-hero { padding:24px 28px; margin:2px 0 22px; border:1px solid #24506a;
          border-radius:20px; background:linear-gradient(110deg,#0c2941,#071b2e 68%,#12364b);
          box-shadow:0 18px 40px #0004; }
      .nexus-kicker { color:#36D399; letter-spacing:.16em; font-size:.76rem; font-weight:800; text-transform:uppercase; }
      .nexus-hero h1 { color:#F3F7FA; margin:.35rem 0; font-size:2rem; }
      .nexus-hero p { color:#B7C8D5; margin:0; }
      .nexus-node { min-height:126px; padding:16px; margin-bottom:12px; border-radius:15px;
          border:1px solid #25465b; background:linear-gradient(150deg,#0d2a41,#071522); }
      .nexus-node b { color:#F3F7FA; font-size:1rem; }
      .nexus-node small { color:#A9BAC8; display:block; margin-top:7px; line-height:1.5; }
      .nexus-pill { display:inline-block; margin-top:10px; padding:4px 9px; border-radius:99px;
          color:#36D399; background:#36D39918; border:1px solid #36D39955; font-size:.72rem; font-weight:700; }
      .nexus-pill.warn { color:#FF9F43; background:#FF9F4318; border-color:#FF9F4355; }
      .nexus-pill.off { color:#FF5D68; background:#FF5D6818; border-color:#FF5D6855; }
      div[data-testid="stTabs"] button { color:#DDE7EF; }
      div[data-testid="stTabs"] button[aria-selected="true"] { color:#36D399; border-color:#36D399; }
      div[data-testid="stExpander"] { border-color:#25465b; border-radius:14px; }
      .ghost-flow { height:270px; margin:14px 0 24px; display:grid; place-items:center; overflow:hidden; position:relative;
          border:1px solid #25465b; border-radius:18px; background:radial-gradient(circle,#103653,#061522 70%); }
      .ghost-core { position:absolute; z-index:2; width:96px; height:96px; display:grid; place-items:center;
          border-radius:50%; color:#071B2E; background:#36D399; font-weight:900; letter-spacing:.12em;
          box-shadow:0 0 20px #36d399aa,0 0 70px #36d39955; animation:ghost-pulse 2.8s ease-in-out infinite; }
      .ghost-ring { width:220px; height:220px; border:1px solid #36d39966; border-radius:50%; position:relative;
          animation:ghost-spin 24s linear infinite; box-shadow:0 0 48px #36d39918,inset 0 0 48px #36d39918; }
      .ghost-ring span { position:absolute; width:36px; height:36px; display:grid; place-items:center; border-radius:50%;
          background:#0c2941; border:1px solid #ff9f43; color:#f3f7fa; font-size:.68rem; font-weight:800;
          box-shadow:0 0 16px #ff9f4388; }
      .ghost-ring span:nth-child(1){top:-18px;left:92px}.ghost-ring span:nth-child(2){top:18px;right:18px}
      .ghost-ring span:nth-child(3){top:92px;right:-18px}.ghost-ring span:nth-child(4){bottom:18px;right:18px}
      .ghost-ring span:nth-child(5){bottom:-18px;left:92px}.ghost-ring span:nth-child(6){bottom:18px;left:18px}
      .ghost-ring span:nth-child(7){top:92px;left:-18px}.ghost-ring span:nth-child(8){top:18px;left:18px}
      .ghost-ring span:nth-child(9){top:53px;left:-10px}.ghost-ring span:nth-child(10){bottom:53px;right:-10px}
      @keyframes ghost-spin { to { transform:rotate(360deg); } }
      @keyframes ghost-pulse { 50% { transform:scale(1.08); box-shadow:0 0 35px #36d399dd,0 0 90px #36d39988; } }
      h1,h2,h3,h4 { color:#F3F7FA; }
      [data-testid="stCaptionContainer"] { color:#A9BAC8; }
      button[kind="primary"] { background:#36D399; border-color:#36D399; color:#061522; font-weight:700; }
    </style>
    """, unsafe_allow_html=True)


def _render_ghost_console(overview: Dict[str, Any]) -> None:
    """Show Ghost's actual model topology and its task stream, without demo controls."""
    from .ghost_institutional_predictive_engine import PAIRS_36_FULL, PRIMARY_ASSETS

    st.subheader("Ghost · cartographie institutionnelle")
    st.markdown(
        '<div class="nexus-hero"><div class="nexus-kicker">GHOST · CARTOGRAPHIE</div>'
        '<h1>Perception → cartographie → décision</h1>'
        '<p>Le graphe Ghost relie les actifs et leurs spreads dans un même espace.</p></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(5)
    for col, (label, value) in zip(cols, (
        ("Actifs suivis", len(PRIMARY_ASSETS)), ("Relations du graphe", len(PAIRS_36_FULL)),
        ("Flux", "Prix · spread · vitesse"), ("Analyse", "Stress · propagation"),
        ("Sortie", "Carte de liquidité"),
    )):
        col.metric(label, value)
    graph_html = """<div class="ghost-flow"><div class="ghost-core">GHOST</div>
      <div class="ghost-ring"><span>USD</span><span>EUR</span><span>GBP</span><span>JPY</span><span>CHF</span>
      <span>CAD</span><span>AUD</span><span>NZD</span><span>XAU</span><span>WTI</span></div></div>"""
    st.markdown(graph_html, unsafe_allow_html=True)
    st.markdown("#### Relations suivies")
    st.dataframe([{"Relation": pair.replace("USD", "/USD", 1) if pair.endswith("USD") else pair[:3] + "/" + pair[3:],
                   "Nœud amont": pair[:3], "Nœud aval": pair[3:]} for pair in PAIRS_36_FULL],
                 use_container_width=True, hide_index=True, height=300)
    st.markdown("#### Journal Ghost")
    ghost_tasks = [task for task in overview.get("tasks", [])
                   if "ghost" in f"{task.get('agent', '')} {task.get('task_type', '')}".casefold()]
    if ghost_tasks:
        st.dataframe([{"Tâche": item.get("task_id"), "Travail": item.get("task_type"),
                       "Agent": item.get("agent"), "Avancement": item.get("status"),
                       "Dernière mise à jour": item.get("updated_at")} for item in ghost_tasks],
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Les tâches Ghost apparaissent ici au fil de leur exécution.")


def _render_payouts(base_url: str) -> None:
    st.subheader("Suivi des revenus et versements")
    st.caption(
        "Nexus suit les montants et rapproche les demandes. Aucun transfert n’est initié ici. "
        "Les revenus restent signalés jusqu’à confirmation par une preuve de la plateforme."
    )
    st.warning(
        "Ne saisis jamais le numéro complet de carte, le CVV, un code OTP ou un mot de passe. "
        "Pour enregistrer une destination, Nexus ne conserve que le fournisseur, le libellé et les 4 derniers chiffres. "
        "La configuration réelle de la carte se fait chez le prestataire de paiement."
    )
    try:
        overview = _get_json(base_url, "/api/v1/payouts/overview")
    except RuntimeError as exc:
        st.error(f"Suivi des paiements indisponible : {exc}")
        return

    balances = overview.get("balances", {})
    if balances:
        st.write("**Soldes connus par Nexus**")
        st.dataframe(
            [
                {"devise": currency, **values}
                for currency, values in balances.items()
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Aucun revenu n’est enregistré. Nexus n’invente pas de solde ni de gain.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Ajouter une destination masquée")
        with st.form("payout_destination_form"):
            provider = st.selectbox("Prestataire", ("Visa Direct / partenaire", "PayPal", "Payoneer", "Banque", "Autre"))
            destination_type = st.selectbox("Type", ("CARD", "WALLET", "BANK"))
            label = st.text_input("Libellé", placeholder="Carte Visa personnelle")
            last4 = st.text_input("4 derniers chiffres uniquement", max_chars=4, placeholder="1234")
            currency = st.text_input("Devise", value="EUR", max_chars=3)
            submitted_destination = st.form_submit_button("Enregistrer le repère masqué")
        if submitted_destination:
            try:
                result = _post_json(base_url, "/api/v1/payouts/destinations", {
                    "provider": provider, "destination_type": destination_type,
                    "label": label, "last4": last4 or None, "currency": currency,
                })
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(
                    f"Repère enregistré. État : {result['setup_status']}. "
                    "Le fournisseur doit encore vérifier/configurer cette destination."
                )

        destinations = overview.get("destinations", [])
        needs_setup = [
            item for item in destinations
            if item.get("setup_status") == "PROVIDER_SETUP_REQUIRED"
        ]
        if needs_setup:
            with st.form("confirm_destination_setup_form"):
                selected_destination = st.selectbox(
                    "Destination configurée chez le prestataire",
                    needs_setup,
                    format_func=lambda item: f"{item['provider']} · {item['label']} · ****{item.get('last4') or '----'}",
                )
                setup_reference = st.text_input(
                    "Référence non sensible de configuration",
                    placeholder="Ex. identifiant de méthode de paiement",
                )
                confirm_setup = st.form_submit_button("Confirmer la configuration externe")
            if confirm_setup:
                try:
                    result = _post_json(
                        base_url,
                        f"/api/v1/payouts/destinations/{selected_destination['destination_id']}/confirm",
                        {"evidence_reference": setup_reference},
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        f"Configuration déclarée manuellement : {result['setup_status']}. "
                        "Nexus n’a pas vérifié le compte auprès du fournisseur."
                    )

    with right:
        st.markdown("#### Signaler un revenu observé")
        with st.form("revenue_entry_form"):
            source = st.text_input("Plateforme/source", placeholder="Nom de la plateforme")
            category = st.selectbox("Catégorie", ("microservices", "ecommerce", "sports", "trading", "other"))
            amount = st.text_input("Montant affiché par la plateforme", placeholder="0.00")
            revenue_currency = st.text_input("Devise du revenu", value="EUR", max_chars=3)
            submitted_revenue = st.form_submit_button("Enregistrer comme signalé")
        if submitted_revenue:
            try:
                result = _post_json(base_url, "/api/v1/payouts/revenue", {
                    "source": source, "category": category,
                    "amount": amount, "currency": revenue_currency,
                })
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(f"Montant enregistré avec le statut {result['status']}.")

    revenues = overview.get("revenues", [])
    reported = [entry for entry in revenues if entry.get("status") == "REPORTED"]
    if reported:
        st.markdown("#### Confirmer un montant payable")
        selected_entry = st.selectbox(
            "Revenu à confirmer",
            reported,
            format_func=lambda entry: (
                f"{entry['source']} · {entry['amount']} {entry['currency']} · {entry['entry_id'][:8]}"
            ),
            key="payout_confirm_entry",
        )
        with st.form("revenue_confirm_form"):
            evidence = st.text_input("Référence/preuve de la plateforme", placeholder="ID de transaction ou référence de solde payable")
            confirm_clicked = st.form_submit_button("Confirmer comme payable")
        if confirm_clicked:
            try:
                result = _post_json(
                    base_url,
                    f"/api/v1/payouts/revenue/{selected_entry['entry_id']}/confirm",
                    {"evidence_reference": evidence},
                )
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(f"Revenu confirmé comme {result['status']}.")

    destinations = overview.get("destinations", [])
    payable_currencies = [
        (currency, values) for currency, values in balances.items()
        if float(values.get("available_to_request", 0)) > 0
    ]
    if destinations and payable_currencies:
        st.markdown("#### Préparer un retrait externe")
        with st.form("payout_order_form"):
            destination = st.selectbox(
                "Destination enregistrée",
                destinations,
                format_func=lambda item: f"{item['provider']} · {item['label']} · {item.get('last4') or 'masqué'} · {item['setup_status']}",
                key="payout_order_destination",
            )
            currency, balance = st.selectbox(
                "Devise / disponible à demander",
                payable_currencies,
                format_func=lambda item: f"{item[0]} · {item[1]['available_to_request']}",
                key="payout_order_currency",
            )
            payout_amount = st.text_input("Montant à suivre", value=balance["available_to_request"])
            submit_order = st.form_submit_button("Créer le suivi de retrait")
        if submit_order:
            try:
                order = _post_json(base_url, "/api/v1/payouts/orders", {
                    "destination_id": destination["destination_id"],
                    "amount": payout_amount, "currency": currency,
                })
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(
                    f"Suivi créé : {order['status']}. Nexus n’a pas envoyé d’argent; "
                    "la demande doit être faite auprès de la plateforme ou du prestataire."
                )

    payouts = overview.get("payouts", [])
    if payouts:
        st.markdown("#### Historique des retraits suivis")
        st.dataframe(
            [
                {
                    "ordre": order["order_id"], "fournisseur": order.get("destination", {}).get("provider"),
                    "destination": order.get("destination", {}).get("label"),
                    "montant": f"{order['amount']} {order['currency']}",
                    "statut": order["status"], "référence externe": order.get("external_reference"),
                    "mis à jour": order["updated_at"],
                }
                for order in payouts
            ],
            use_container_width=True,
            hide_index=True,
        )
        active_orders = [
            order for order in payouts
            if order["status"] in {
                "WAITING_PROVIDER_SETUP", "READY_FOR_MANUAL_REQUEST", "REQUESTED_EXTERNALLY",
                "PROCESSING", "REVIEW_REQUIRED",
            }
        ]
        if active_orders:
            order = st.selectbox(
                "Ordre à rapprocher",
                active_orders,
                format_func=lambda item: f"{item['amount']} {item['currency']} · {item['status']} · {item['order_id'][:8]}",
                key="payout_reconcile_order",
            )
            with st.form("payout_reconcile_form"):
                payout_status = st.selectbox(
                    "État confirmé dans le compte externe",
                    ("REQUESTED_EXTERNALLY", "PROCESSING", "PAID", "FAILED", "REVIEW_REQUIRED", "CANCELLED"),
                )
                external_reference = st.text_input("Référence externe requise", placeholder="ID affiché par la plateforme")
                reconcile_clicked = st.form_submit_button("Enregistrer le statut externe")
            if reconcile_clicked:
                try:
                    updated = _post_json(
                        base_url,
                        f"/api/v1/payouts/orders/{order['order_id']}/status",
                        {"status": payout_status, "external_reference": external_reference},
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Statut rapproché : {updated['status']}.")

    if revenues:
        st.markdown("#### Journal des revenus")
        st.dataframe(
            [
                {
                    "source": item["source"], "catégorie": item["category"],
                    "montant": f"{item['amount']} {item['currency']}",
                    "statut": item["status"], "référence": item.get("evidence_reference"),
                    "date": item["earned_at"],
                }
                for item in revenues
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_dashboard() -> None:
    st.set_page_config(
        page_title="Nexus · Operational Command Center",
        page_icon="N",
        layout="wide",
    )
    _inject_nexus_theme()
    st.markdown("""
    <div class="nexus-hero">
      <div class="nexus-kicker">NEXUS · AUTONOMOUS OPERATIONS</div>
      <h1>Centre de pilotage</h1>
      <p>Microservices · E-commerce · Trading · Paris sportifs · Ghost</p>
    </div>
    """, unsafe_allow_html=True)

    default_url = os.getenv("NEXUS_API_BASE_URL", "http://127.0.0.1:8000")
    base_url = default_url

    _handle_oauth_callback(base_url)

    try:
        overview = _get_json(base_url, "/api/v1/operational/overview")
    except RuntimeError:
        st.info("Les tâches se rechargent automatiquement dès que le service répond.")
        return

    overview_tabs = st.tabs([
        "Vue globale", "Microservices", "E-commerce", "Trading", "Paris sportifs",
        "Ghost", "Agents IA", "Comptes", "Revenus",
    ])
    missions = overview.get("missions", [])
    tasks = overview.get("tasks", [])

    with overview_tabs[0]:
        st.subheader("Missions")
        if missions:
            st.dataframe(
                [
                    {
                        "mission_id": mission["mission_id"],
                        "objectif": mission["objective"],
                        "statut": mission["status"],
                        "tâche courante": mission["current_task_id"],
                        "tâches vérifiées": mission["progress"]["verified_tasks"],
                        "tâches totales": mission["progress"]["total_tasks"],
                        "progression réelle": mission["progress"]["ratio"],
                    }
                    for mission in missions
                ],
                use_container_width=True,
            )
        else:
            st.caption("Aucune mission enregistrée.")
        st.subheader("Tâches")
        if tasks:
            st.dataframe(
                [
                    {
                        "task_id": task["task_id"],
                        "mission_id": task["mission_id"],
                        "agent": task["agent"],
                        "statut": task["status"],
                        "mode": task["execution_mode"],
                        "updated_at": task["updated_at"],
                    }
                    for task in tasks
                ],
                use_container_width=True,
            )
        else:
            st.caption("Aucune tâche enregistrée.")

    def render_category(title: str, category: str, keywords: tuple[str, ...]) -> None:
        st.subheader(title)
        try:
            integration_status = _get_json(base_url, "/api/v1/integrations/status")
            catalog = [item for item in integration_status.get("platform_catalog", []) if item.get("category") == category]
        except RuntimeError as exc:
            catalog = []
            st.warning(f"Inventaire des plateformes indisponible : {exc}")
        matching = [
            task for task in tasks
            if any(
                keyword in f"{task.get('task_type', '')} {task.get('agent', '')}".casefold()
                for keyword in keywords
            )
        ]
        st.write("**Plateformes**")
        if catalog:
            for start in range(0, len(catalog), 2):
                columns = st.columns(2)
                for column, platform in zip(columns, catalog[start:start + 2]):
                    with column.container(border=True):
                        st.markdown(f"#### {platform.get('name', 'Plateforme')}")
                        st.caption(platform.get("source", "Plateforme répertoriée"))
                        st.markdown(f"**État :** {platform.get('connection_mode', 'À configurer')}")
                        url = platform.get("url")
                        if url:
                            st.link_button("Ouvrir l’application Android officielle", url, use_container_width=True)
                        else:
                            st.caption("Aucun lien d’application officielle vérifié dans le catalogue.")
        else:
            st.caption("Aucune plateforme déclarée pour cette catégorie.")
        st.markdown("**Tâches du département**")
        if matching:
            st.dataframe(
                [
                    {
                        "task_id": task["task_id"],
                        "type": task["task_type"],
                        "agent": task["agent"],
                        "statut": task["status"],
                        "mode": task["execution_mode"],
                        "updated_at": task["updated_at"],
                    }
                    for task in matching
                ],
                use_container_width=True,
            )
        else:
            st.caption("Aucune tâche réellement enregistrée dans cette catégorie.")

    def render_sports_portal() -> None:
        """Show official Android app install pages declared in the sports catalog."""
        st.subheader("Applications Android de paris sportifs")
        st.caption("Google Play ouvre l’installation officielle; les opérateurs qui distribuent un APK ouvrent leur propre page de téléchargement. Nexus ne stocke pas de copie d’APK et les applications s’installent sur Android.")
        try:
            integration_status = _get_json(base_url, "/api/v1/integrations/status")
            catalog = [
                item for item in integration_status.get("platform_catalog", [])
                if item.get("category") == "sports" and item.get("url")
            ]
        except RuntimeError as exc:
            st.error(f"Les fiches des applications Android ne sont pas disponibles : {exc}")
            return

        for start in range(0, len(catalog), 2):
            columns = st.columns(2)
            for column, platform in zip(columns, catalog[start:start + 2]):
                with column.container(border=True):
                    st.markdown(f"### {platform['name']}")
                    st.caption(platform.get("source", "Plateforme sportive"))
                    st.link_button(
                        "Installer depuis Google Play"
                        if platform.get("status") == "ANDROID_APP_GOOGLE_PLAY"
                        else "Télécharger l’APK officiel",
                        platform["url"],
                        use_container_width=True,
                    )
        if not catalog:
            st.caption("Aucune plateforme sportive n’est déclarée dans le catalogue.")

        st.divider()
        st.subheader("Gemini en ligne · contexte Nexus")
        st.caption("Prépare le contexte dans Nexus, puis ouvre Gemini avec ton compte Google. Gemini répond dans son interface en ligne; Nexus ne transmet rien à une API Gemini.")
        sports_question = st.text_area(
            "Rencontre, cotes et éléments à examiner",
            placeholder="Ex. équipe A – équipe B, compétition, date, cotes observées, statistiques ou question…",
            key="nexus_sports_gemini_question",
        )
        if st.button("Préparer le contexte pour Gemini", key="nexus_prepare_gemini_context"):
            if not sports_question.strip():
                st.warning("Ajoute une rencontre ou une question pour préparer le contexte.")
            else:
                st.session_state["nexus_gemini_sports_context"] = (
                    "Tu es mon assistant d’analyse sportive dans Nexus. Analyse les informations ci-dessous. "
                    "Vérifie les éléments récents avec des sources en ligne, indique les dates et les liens, "
                    "distingue faits vérifiés et incertitudes, et signale les données manquantes. "
                    "Ne prétends pas garantir un résultat.\n\n"
                    f"Contexte fourni par Nexus :\n{sports_question.strip()}"
                )
        sports_context = st.session_state.get("nexus_gemini_sports_context", "")
        if sports_context:
            st.text_area("Contexte à copier dans Gemini", value=sports_context, height=180, key="nexus_gemini_context_preview")
        st.link_button("Ouvrir Gemini en ligne", "https://gemini.google.com/app", use_container_width=True)
        st.caption("Dans Gemini, colle le contexte préparé ci-dessus. Sur Android, l’onglet Gemini en ligne de l’application Nexus propose aussi le partage direct vers l’application Gemini installée.")

    for tab, title, category, keywords in (
        (overview_tabs[1], "Microservices", "microservices", ("microservice", "micro-task", "gig", "service")),
        (overview_tabs[2], "E-commerce", "ecommerce", ("ecommerce", "e-commerce", "product", "affiliate", "catalogue")),
        (overview_tabs[3], "Trading", "trading", ("trading", "trade", "market", "broker", "mt5")),
        (overview_tabs[4], "Paris sportifs", "sports", ("sports", "bet", "wager", "football", "1xbet")),
    ):
        if category == "sports":
            continue
        with tab:
            render_category(title, category, keywords)

    with overview_tabs[4]:
        render_sports_portal()

    with overview_tabs[5]:
        _render_ghost_console(overview)

    with overview_tabs[6]:
        st.subheader("Chat IA · Codex / Claude")
        st.caption("Claude en ligne peut recevoir le contexte préparé ici. L’ouverture de Claude ne transmet pas automatiquement les comptes ni les tâches Nexus.")
        selected_agent = st.selectbox("Agent", ("gpt", "claude"), key="nexus_advisory_agent")
        selected_domain = st.selectbox("Domaine", ("general", "microservices", "ecommerce", "trading", "sports", "ghost"), key="nexus_advisory_domain")
        advisory_message = st.text_area("Objectif ou question", key="nexus_advisory_message")
        if st.button("Demander une recommandation", key="nexus_advisory_submit"):
            if not advisory_message.strip():
                st.warning("Saisissez un objectif ou une question.")
            else:
                try:
                    st.session_state["nexus_advisory_response"] = _post_json(
                        base_url, f"/api/v1/advisory/{selected_agent}",
                        {"message": advisory_message, "domain": selected_domain},
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
        if st.session_state.get("nexus_advisory_response"):
            st.json(st.session_state["nexus_advisory_response"])

        st.markdown("#### Préparer le travail pour Claude en ligne")
        claude_goal = st.text_area(
            "Travail à lancer avec Claude",
            value="Repère les missions réalisables, prépare les offres de services et le plan de lancement des boutiques sans inventer de compte, commande ou revenu.",
            key="nexus_claude_goal",
        )
        try:
            claude_platforms = [
                item.get("name", "") for item in _get_json(base_url, "/api/v1/integrations/status").get("platform_catalog", [])
                if item.get("category") in {"microservices", "ecommerce"}
            ]
        except RuntimeError:
            claude_platforms = []
        active_work = [
            f"{task.get('task_id')} · {task.get('task_type')} · {task.get('status')}"
            for task in tasks if task.get("status") in {"PLANNED", "QUEUED", "RUNNING", "WAITING_APPROVAL", "WAITING_HUMAN"}
        ]
        claude_context = (
            "Tu travailles avec Nexus sur les départements microservices et e-commerce. "
            f"Plateformes affichées : {', '.join(claude_platforms) if claude_platforms else 'catalogue indisponible'}. "
            "Les comptes ne sont pas présumés connectés. Propose des actions légales et concrètes, "
            "respecte les règles des plateformes, ne crée pas de faux comptes, n’engage pas de dépense, "
            "ne prétends pas avoir créé une boutique ou terminé une tâche, et indique les accès ou contenus "
            "qu’il faut configurer directement chez chaque plateforme. Les revenus doivent rester à zéro "
            "tant qu’ils ne sont pas étayés par une preuve.\n\nTravail Nexus actuellement suivi : "
            f"{'; '.join(active_work) if active_work else 'aucune tâche active enregistrée'}.\n\nObjectif : "
            f"{claude_goal.strip()}"
        )
        st.text_area("Contexte prêt à copier dans Claude", value=claude_context, height=170, key="nexus_claude_context_preview")
        st.link_button("Ouvrir Claude en ligne", "https://claude.ai/new", use_container_width=True)

    with overview_tabs[7]:
        st.subheader("Comptes et plateformes")
        try:
            integrations = _get_json(base_url, "/api/v1/integrations/status")
        except RuntimeError:
            st.info("Les comptes se rechargent automatiquement dès que le service répond.")
        else:
            _render_managed_connections(base_url, integrations)

    with overview_tabs[8]:
        _render_payouts(base_url)
