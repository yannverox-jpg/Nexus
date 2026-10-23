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
    storage = connection_data.get("storage", {})
    if storage.get("remember_me_ready"):
        st.success("Le stockage chiffré et persistant permet les sessions mémorisées.")
    elif storage.get("reason") == "encryption_key_missing":
        st.warning("Sessions mémorisées indisponibles : la clé de chiffrement doit être configurée dans les secrets Render.")
    else:
        st.warning("Sessions mémorisées indisponibles : un stockage persistant est requis sur Render.")

    providers = connection_data.get("providers", [])
    if not providers:
        st.info("Aucun fournisseur OAuth configuré. Chaque plateforme doit proposer une intégration officielle compatible.")
        return
    for provider in providers:
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.markdown(f"**{provider.get('name', provider.get('provider_id'))}**")
            scopes = ", ".join(provider.get("scopes", [])) or "aucune"
            left.caption(f"État : {provider.get('status', 'NOT_CONNECTED')} · Autorisations : {scopes}")
            if provider.get("error_code"):
                left.caption(f"Action requise : {provider['error_code']}")
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
      .nexus-note { padding:12px 15px; border-left:3px solid #FF9F43; background:#FF9F4312;
          color:#D7E2EA; border-radius:4px 12px 12px 4px; }
      h1,h2,h3,h4 { color:#F3F7FA; }
      [data-testid="stCaptionContainer"] { color:#A9BAC8; }
      button[kind="primary"] { background:#36D399; border-color:#36D399; color:#061522; font-weight:700; }
    </style>
    """, unsafe_allow_html=True)


def _render_ghost_console(base_url: str, overview: Dict[str, Any]) -> None:
    st.subheader("Ghost · poste de métamorphose")
    st.caption("Le graphe, le journal et les contrôles affichent leurs sources et leurs modes. Les essais ci-dessous n’envoient aucun ordre.")
    stages = [
        ("Kernel", "Coordination et contrôles", "CODE PRÉSENT", "ok"),
        ("Perception", "Cotations et flux MT5", "FLUX REQUIS", "off"),
        ("Reconstruction", "Contexte marché", "DONNÉES REQUISES", "warn"),
        ("Cartographie", "Graphe d’actifs et spreads", "MODÈLE DISPONIBLE", "ok"),
        ("Analyse", "Stress et propagation", "SCÉNARIO DISPONIBLE", "ok"),
        ("Mémoire", "Journal opérationnel", "PERSISTANCE RENDER À CONFIGURER", "warn"),
        ("Prédiction", "Spread attendu / hypothèse", "CODE PARTIEL", "warn"),
        ("Décision", "Proposition contrôlée", "PROPOSITION SEULEMENT", "warn"),
        ("Exécution", "Ordres MT5", "AUCUN ORDRE ENVOYÉ", "off"),
    ]
    for start in range(0, len(stages), 3):
        cols = st.columns(3)
        for col, (name, desc, status, kind) in zip(cols, stages[start:start + 3]):
            col.markdown(
                f'<div class="nexus-node"><b>{name}</b><small>{desc}</small>'
                f'<span class="nexus-pill {"warn" if kind == "warn" else "off" if kind == "off" else ""}">{status}</span></div>',
                unsafe_allow_html=True,
            )
    stage_names = [stage[0] for stage in stages]
    selected_stage = st.select_slider("Prévisualiser la transformation", options=stage_names, value="Cartographie")
    stage_index = stage_names.index(selected_stage)
    st.progress((stage_index + 1) / len(stage_names), text=f"Aperçu de l’organe {stage_index + 1}/9 · {selected_stage}")
    st.caption("Cette progression est une prévisualisation de l’interface no-code; seul le scénario de marché ci-dessous exécute le calcul Ghost.")

    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("#### MT5 · test de connexion en lecture seule")
        st.caption("Vérifie le terminal et lit quelques cotations configurées. L’essai ne crée ni ne modifie aucune position.")
        if st.button("Tester le terminal MT5", key="ghost_mt5_preflight", type="primary"):
            try:
                st.session_state["ghost_mt5_result"] = _get_json(base_url, "/api/v1/ghost/mt5/preflight")
            except RuntimeError as exc:
                st.session_state["ghost_mt5_result"] = {"status": "API_UNAVAILABLE", "detail": str(exc), "orders_submitted": 0}
        mt5_result = st.session_state.get("ghost_mt5_result")
        if mt5_result:
            status = mt5_result.get("status", "UNKNOWN")
            if status == "CONNECTED":
                st.success(f"Terminal joignable · {len(mt5_result.get('quotes', []))} cotation(s) lue(s) · 0 ordre envoyé")
                st.dataframe(mt5_result.get("quotes", []), use_container_width=True, hide_index=True)
            else:
                st.error(f"MT5 : {status}")
                st.caption(mt5_result.get("detail") or "Aucune cotation confirmée. Aucun ordre n’a été envoyé.")
        else:
            st.info("Pas encore testé. Render héberge Nexus sur Linux; un terminal MT5 local nécessite un pont Windows configuré pour fournir des données réelles.")

    with right:
        st.markdown("#### Aperçu Ghost · scénario contrôlé")
        st.caption("Entre un bid/ask observé ou un scénario. Les valeurs saisies ne sont pas des cotations live.")
        with st.form("ghost_scenario_form"):
            symbol = st.selectbox("Instrument", ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "WTIUSD"))
            bid_text = st.text_input("Bid", placeholder="Valeur observée")
            ask_text = st.text_input("Ask", placeholder="Valeur observée")
            terminal_latency = st.number_input("Latence terminal observée (ms)", min_value=0.0, value=0.0, step=0.1)
            usd_speed = st.number_input("Vitesse USD (unité du modèle)", value=0.0, step=0.1)
            submitted = st.form_submit_button("Calculer la prévisualisation", type="primary")
        if submitted:
            try:
                bid = float(bid_text.strip())
                ask = float(ask_text.strip())
                result = _post_json(base_url, "/api/v1/ghost/preview", {
                    "symbol": symbol, "bid": bid, "ask": ask,
                    "terminal_latency_ms": terminal_latency, "usd_speed": usd_speed,
                })
            except (ValueError, RuntimeError) as exc:
                st.error(f"Prévisualisation non calculée : {exc}")
            else:
                st.session_state["ghost_scenario_result"] = result

    result = st.session_state.get("ghost_scenario_result")
    if result:
        st.markdown("#### Résultat de la prévisualisation")
        st.caption(f"Source : {result['source']} · mode {result['mode']} · aucun ordre envoyé · calcul Ghost {result['ghost_compute_latency_ms']} ms")
        spread = result["spread_model"]
        cols = st.columns(5)
        cols[0].metric("Spread calculé", result["spread"])
        cols[1].metric("Spread attendu du modèle", spread["e_expected_spread"])
        cols[2].metric("Stress du spread", spread["z_spread_stress"])
        cols[3].metric("État du carnet (proxy)", spread["orderbook_status"])
        cols[4].metric("Latence MT5 saisie", f"{result['input_terminal_latency_ms']} ms" if result.get("input_terminal_latency_ms") else "Non fournie")
        st.bar_chart({
            "Spread saisi": [spread["s_current"]],
            "Référence du modèle": [spread["e_expected_spread"]],
        }, height=180)
        if result.get("propagation_hypotheses"):
            st.dataframe(result["propagation_hypotheses"], use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune hypothèse de propagation déclenchée par les valeurs de ce scénario.")
        st.markdown('<div class="nexus-note">Le graphe de liquidité actuel utilise le bid/ask et un proxy de stress; il ne lit pas la profondeur réelle du carnet. Le spread attendu est une référence codée, pas une prévision apprise.</div>', unsafe_allow_html=True)

    st.markdown("#### Journal des tâches Ghost")
    ghost_tasks = [
        task for task in overview.get("tasks", [])
        if "ghost" in f"{task.get('agent', '')} {task.get('task_type', '')}".casefold()
    ]
    if ghost_tasks:
        st.dataframe([
            {"Tâche": item.get("task_id"), "Type": item.get("task_type"),
             "Agent": item.get("agent"), "État": item.get("status"),
             "Mode": item.get("execution_mode"), "Mis à jour": item.get("updated_at")}
            for item in ghost_tasks
        ], use_container_width=True, hide_index=True)
    else:
        st.info("Le journal ne contient pas encore de tâche Ghost. Les étapes ci-dessus décrivent le code détecté, pas un cycle d’exécution déjà réalisé.")


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


def _show_records(label: str, records: Any) -> None:
    st.subheader(label)
    if records:
        st.json(records)
    else:
        st.caption("Aucune donnée enregistrée dans OperationalJournal.")


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
    with st.sidebar:
        st.header("Connexion à l’API opérationnelle")
        base_url = st.text_input("URL de base", value=default_url)
        st.button("Rafraîchir les données")

    _handle_oauth_callback(base_url)

    try:
        overview = _get_json(base_url, "/api/v1/operational/overview")
    except RuntimeError as exc:
        st.error(str(exc))
        st.info("Aucun état local ou legacy n’est utilisé comme solution de repli.")
        return

    runtime = overview["runtime"]
    active_session = runtime.get("active_session")
    latest_session = runtime.get("latest_session")
    last_activity = runtime.get("last_activity")
    summary_columns = st.columns(4)
    summary_columns[0].metric("Session active", "Oui" if active_session else "Non")
    summary_columns[1].metric(
        "Runtime", active_session["status"] if active_session else (
            latest_session["status"] if latest_session else "Non enregistré"
        )
    )
    summary_columns[2].metric("Tâches journalisées", len(overview.get("tasks", [])))
    summary_columns[3].metric("Dernière activité", str(last_activity["occurred_at"])[:19] if last_activity else "Aucune")

    try:
        storage = _get_json(base_url, "/api/v1/storage")
    except RuntimeError:
        storage = {"durable_on_render": False, "database_path": "inconnu"}
    if storage.get("durable_on_render"):
        st.success(f"Mémoire SQLite sur disque persistant : {storage['database_path']}")
    else:
        st.warning(
            "Mémoire SQLite active mais éphémère sur Render : le journal peut être perdu au redémarrage. "
            "Le disque durable n’est pas encore configuré."
        )

    overview_tabs = st.tabs(
        [
            "Vue globale", "Mission", "Tâche", "Timeline", "Exécution / preuves", "Recovery",
            "Microservices", "E-commerce", "Trading", "Paris sportifs", "Ghost · Laboratoire",
            "Agents IA", "Connexions", "Revenus & paiements",
        ]
     )
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
        st.subheader("Tasks — statuts canoniques")
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
        st.caption(
            "La progression correspond uniquement au ratio de tâches VERIFIED "
            "enregistrées / tâches totales; elle n’est pas une estimation."
        )

    with overview_tabs[1]:
        mission_ids = [mission["mission_id"] for mission in missions]
        if not mission_ids:
            st.caption("Aucune mission à détailler.")
        else:
            selected_mission = st.selectbox("Mission", mission_ids)
            try:
                detail = _get_json(
                    base_url, f"/api/v1/operational/missions/{selected_mission}"
                )
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.json({key: detail[key] for key in (
                    "mission_id", "objective", "status", "current_task_id",
                    "progress", "task_counts", "metadata",
                ) if key in detail})
                st.dataframe(
                    [
                        {
                            "task_id": task["task_id"],
                            "agent": task["agent"],
                            "statut": task["status"],
                            "mode": task["execution_mode"],
                            "updated_at": task["updated_at"],
                        }
                        for task in detail.get("tasks", [])
                    ],
                    use_container_width=True,
                )
                _show_records("Timeline de la mission", detail.get("timeline"))

    with overview_tabs[2]:
        task_ids = [task["task_id"] for task in tasks]
        if not task_ids:
            st.caption("Aucune tâche à détailler.")
        else:
            selected_task = st.selectbox("Tâche", task_ids)
            try:
                detail = _get_json(
                    base_url, f"/api/v1/operational/tasks/{selected_task}"
                )
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.json({key: detail.get(key) for key in (
                    "task_id", "mission_id", "mission_objective", "task_type",
                    "agent", "status", "priority", "execution_mode", "correlation_id",
                    "success_criteria", "result", "error",
                )})
                for key, label in (
                    ("task_events", "Événements"),
                    ("task_steps", "Étapes"),
                    ("agent_actions", "Actions agent"),
                    ("decisions", "Décisions"),
                    ("execution_attempts", "Tentatives d’exécution"),
                    ("tool_calls", "Appels d’outils"),
                    ("proofs", "Preuves / vérification"),
                    ("failures", "Erreurs"),
                    ("recovery_actions", "Récupérations"),
                    ("approvals", "Approbations"),
                    ("observations", "Observations"),
                    ("outcomes", "Outcomes"),
                ):
                    _show_records(label, detail.get(key))

    with overview_tabs[3]:
        _show_records("Événements réels du journal", overview.get("timeline"))

    with overview_tabs[4]:
        _show_records("Tentatives d’exécution", overview.get("execution_attempts"))
        _show_records("Tool calls (mode REAL / SIMULATED)", overview.get("tool_calls"))
        _show_records("Preuves et état de vérification", overview.get("proofs"))
        st.info("Un tool call COMPLETED n’implique pas qu’une tâche soit VERIFIED.")

    with overview_tabs[5]:
        _show_records("Failures", overview.get("failures"))
        _show_records("Recovery actions", overview.get("recovery_actions"))
        _show_records("Tâches en attente humaine", overview.get("waiting_human_tasks"))
        _show_records("Outcomes persistés", overview.get("outcomes"))
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
        connected = sum(1 for item in catalog if str(item.get("status", "")).upper() in {"CONNECTED", "ACTIVE", "READY"})
        running = sum(1 for item in matching if item.get("status") in {"RUNNING", "IN_PROGRESS"})
        verified = sum(1 for item in matching if item.get("status") == "VERIFIED")
        metrics = st.columns(4)
        metrics[0].metric("Plateformes au catalogue", len(catalog))
        metrics[1].metric("Connexions vérifiées", connected)
        metrics[2].metric("Tâches en cours", running)
        metrics[3].metric("Tâches vérifiées", verified)
        st.write("**Plateformes de ce département**")
        if catalog:
            st.dataframe(
                [
                    {"Plateforme": item.get("name"), "État": item.get("status"),
                     "Mode de connexion": item.get("connection_mode"), "Source": item.get("source")}
                    for item in catalog
                ], use_container_width=True, hide_index=True,
            )
        else:
            st.caption("Aucune plateforme déclarée pour cette catégorie.")
        st.markdown("**Activité réelle du journal**")
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
        st.caption("Les compteurs viennent du journal opérationnel; les plateformes sans connexion confirmée restent signalées comme telles.")

    for tab, title, category, keywords in (
        (overview_tabs[6], "Microservices", "microservices", ("microservice", "micro-task", "gig", "service")),
        (overview_tabs[7], "E-commerce", "ecommerce", ("ecommerce", "e-commerce", "product", "affiliate", "catalogue")),
        (overview_tabs[8], "Trading", "trading", ("trading", "trade", "market", "broker", "mt5")),
        (overview_tabs[9], "Paris sportifs", "sports", ("sports", "bet", "wager", "football", "1xbet")),
    ):
        with tab:
            render_category(title, category, keywords)

    with overview_tabs[10]:
        _render_ghost_console(base_url, overview)

    with overview_tabs[11]:
        st.subheader("Chat IA · Codex / Claude / Gemini")
        st.caption("Chaque réponse est produite par l’API officielle du fournisseur configuré. Les modèles ne sont pas l’agent Codex de cette conversation.")
        try:
            provider_status = _get_json(base_url, "/api/v1/integrations/status").get("ai_providers", [])
        except RuntimeError:
            provider_status = []
        if provider_status:
            status_columns = st.columns(3)
            for col, item in zip(status_columns, provider_status):
                state = "CLÉ PRÉSENTE · NON TESTÉE" if item.get("connector_available") else "CLÉ API ABSENTE"
                col.metric(item.get("label", item.get("provider_id")), state, item.get("model"))
        else:
            st.warning("État des fournisseurs indisponible.")
        st.caption("Les clés manquantes doivent être ajoutées aux secrets Render; elles ne sont pas reprises de Codex, Claude ou Gemini ouverts dans d’autres applications.")
        selected_agent = st.selectbox("Agent", ("gpt", "gemini", "claude"), key="nexus_advisory_agent")
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

    with overview_tabs[12]:
        st.subheader("Diagnostic des connexions")
        try:
            integrations = _get_json(base_url, "/api/v1/integrations/status")
        except RuntimeError as exc:
            st.error(f"Diagnostic indisponible : {exc}")
        else:
            _render_managed_connections(base_url, integrations)
            st.divider()
            browser = integrations["browser"]
            st.write("**Rôles déclarés dans Nexus**")
            role_rows = [
                {"domaine": domain, "agent": agent, "rôle": role}
                for domain, assignments in integrations["agent_roles"].items()
                for agent, role in assignments.items()
            ]
            st.dataframe(role_rows, use_container_width=True)
            st.write("**État des connexions IA**")
            st.dataframe(
                [
                    {
                        "fournisseur": item["label"],
                        "statut": item["status"],
                        "connecteur disponible": item["connector_available"],
                        "peut exécuter": item["can_execute_actions"],
                    }
                    for item in integrations["ai_providers"]
                ],
                use_container_width=True,
            )
            st.caption("NOT_CONNECTED signifie qu’aucun connecteur fournisseur IA n’est configuré. La session Codex de cette conversation n’est pas réutilisée.")
            st.write("**Navigateur**")
            st.json(browser)
            st.write("**Navigation web en lecture seule**")
            st.caption("La cible doit figurer dans NEXUS_BROWSER_ALLOWED_HOSTS. Cette navigation sert au diagnostic; les connexions de compte passent par OAuth officiel.")
            selected_browser = st.selectbox("Navigateur", ("chromium", "firefox"), key="nexus_browser_engine")
            requested_url = st.text_input("Adresse web autorisée", key="nexus_browser_url")
            if st.button("Ouvrir et observer", key="nexus_browser_navigate"):
                try:
                    st.session_state["nexus_browser_observation"] = _post_json(
                        base_url, "/api/v1/browser/navigate", {
                            "url": requested_url,
                            "browser": selected_browser,
                        }, timeout=210,
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
            if st.session_state.get("nexus_browser_observation"):
                st.json(st.session_state["nexus_browser_observation"])
            st.write("**Inventaire des plateformes**")
            targets = integrations.get("platform_catalog", [])
            if targets:
                st.dataframe(
                    [
                        {
                            "name": target.get("name", "unknown"),
                            "category": target.get("category", "unknown"),
                            "source": target.get("source", ""),
                            "status": target.get("status", "UNKNOWN"),
                            "connection_mode": target.get("connection_mode", "Not configured"),
                        }
                        for target in targets
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                for target in targets:
                    left, right = st.columns([4, 1])
                    left.write(
                        f"{target.get('name', 'unknown')} · "
                        f"{target.get('host', 'hôte non configuré')} · "
                        f"{target.get('status', 'UNKNOWN')}"
                    )
                    if target.get("url") and target.get("navigation_ready"):
                        right.link_button("Ouvrir", target["url"], use_container_width=True)
                    else:
                        right.caption("Non connecté")
            else:
                st.info("Le catalogue fixe ne contient aucune plateforme pour cette catégorie.")
            st.caption("Un statut de catalogue ne prouve pas qu’un compte est connecté. Consulte la section Connexions de comptes ci-dessus pour l’état OAuth réel.")

    with overview_tabs[13]:
        _render_payouts(base_url)
