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


def _post_json(base_url: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Browser operation unavailable: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Browser operation returned an invalid response")
    return data


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
    st.title("Nexus · Operational Command Center")
    st.caption(
        "Vue en lecture seule alimentée exclusivement par OperationalJournal. "
        "EXECUTED et VERIFIED restent des états distincts."
    )

    default_url = os.getenv("NEXUS_API_BASE_URL", "http://127.0.0.1:8000")
    with st.sidebar:
        st.header("Connexion à l’API opérationnelle")
        base_url = st.text_input("URL de base", value=default_url)
        st.button("Rafraîchir les données")

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
    summary_columns = st.columns(3)
    summary_columns[0].write(
        "**Session active**\n\n" +
        (active_session["session_id"] if active_session else "Aucune")
    )
    summary_columns[1].write(
        "**État du runtime**\n\n" +
        (active_session["status"] if active_session else (
            latest_session["status"] if latest_session else "Non enregistré"
        ))
    )
    summary_columns[2].write(
        "**Dernière activité**\n\n" +
        (str(last_activity["occurred_at"]) if last_activity else "Aucune")
    )

    try:
        storage = _get_json(base_url, "/api/v1/storage")
    except RuntimeError:
        storage = {"durable_on_render": False, "database_path": "inconnu"}
    if storage.get("durable_on_render"):
        st.success(f"Mémoire SQLite sur disque persistant : {storage['database_path']}")
    else:
        st.warning(
            "Mémoire SQLite active, mais éphémère sur Render. Pour la conserver après "
            "redémarrage/déploiement, attachez un disque persistant payant monté sur "
            "/var/data et définissez NEXUS_OPERATIONAL_DB_PATH=/var/data/nexus_operational.db."
        )

    overview_tabs = st.tabs(
        [
            "Vue globale", "Mission", "Tâche", "Timeline", "Exécution / preuves", "Recovery",
            "Microservices", "E-commerce", "Trading", "Paris sportifs", "Chat central",
            "Connexions", "Revenus & paiements",
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
        st.write("**Cibles web configurées**")
        if catalog:
            st.dataframe(catalog, use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune plateforme déclarée pour cette catégorie.")
        matching = [
            task for task in tasks
            if any(
                keyword in f"{task.get('task_type', '')} {task.get('agent', '')}".casefold()
                for keyword in keywords
            )
        ]
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
        st.info(
            "Le catalogue Nexus indique les plateformes demandées et leur état de connexion. "
            "La navigation générique reste en lecture seule et exige un hôte autorisé."
        )

    for tab, title, category, keywords in (
        (overview_tabs[6], "Microservices", "microservices", ("microservice", "micro-task", "gig", "service")),
        (overview_tabs[7], "E-commerce", "ecommerce", ("ecommerce", "e-commerce", "product", "affiliate", "catalogue")),
        (overview_tabs[8], "Trading", "trading", ("trading", "trade", "market", "broker", "mt5")),
        (overview_tabs[9], "Paris sportifs", "sports", ("sports", "bet", "wager", "football", "1xbet")),
    ):
        with tab:
            render_category(title, category, keywords)

    with overview_tabs[10]:
        st.subheader("Chat de coordination")
        st.caption("Les réponses des fournisseurs sont des recommandations. Elles ne constituent ni preuve ni autorisation financière et ne déclenchent aucune action externe.")
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

    with overview_tabs[11]:
        st.subheader("Diagnostic des connexions")
        try:
            integrations = _get_json(base_url, "/api/v1/integrations/status")
        except RuntimeError as exc:
            st.error(f"Diagnostic indisponible : {exc}")
        else:
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
            st.caption("La cible doit figurer dans NEXUS_BROWSER_ALLOWED_HOSTS. Nexus ne remplit aucun formulaire et ne se connecte pas aux comptes.")
            selected_browser = st.selectbox("Navigateur", ("chromium", "firefox"), key="nexus_browser_engine")
            requested_url = st.text_input("Adresse web autorisée", key="nexus_browser_url")
            if st.button("Ouvrir et observer", key="nexus_browser_navigate"):
                try:
                    st.session_state["nexus_browser_observation"] = _post_json(
                        base_url, "/api/v1/browser/navigate", {
                            "url": requested_url,
                            "browser": selected_browser,
                        }
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
            st.caption(
                "Un statut configuré ne signifie pas qu’une session de compte est ouverte. "
                "Nexus ne récupère aucun cookie, mot de passe ou session. Les connexions de compte restent manuelles."
            )

    with overview_tabs[12]:
        _render_payouts(base_url)
