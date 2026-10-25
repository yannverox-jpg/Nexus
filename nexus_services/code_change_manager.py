"""Approval-gated code adaptation through GitHub pull requests.

Nexus never edits the live process or merges its own changes. When configured,
it creates a dedicated branch and draft PR so repository checks and a human
review must succeed before any change reaches the base branch.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def code_change_status() -> dict[str, Any]:
    repository = os.getenv("NEXUS_GITHUB_REPOSITORY", "").strip()
    token = os.getenv("NEXUS_GITHUB_TOKEN", "").strip()
    base_branch = os.getenv("NEXUS_GITHUB_BASE_BRANCH", "main").strip() or "main"
    configured = bool(repository and token and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository))
    return {
        "mode": "DRAFT_PULL_REQUEST" if configured else "PROPOSAL_ONLY",
        "configured": configured,
        "repository_configured": bool(repository),
        "token_configured": bool(token),
        "base_branch": base_branch,
        "live_self_editing": False,
        "auto_merge": False,
        "requires_ci_and_human_review": True,
    }


class CodeChangeManager:
    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def _request(self, method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=data,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Nexus-approval-gated-code-adaptation",
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            # Do not include upstream body: it may echo sensitive repository metadata.
            raise RuntimeError(f"GitHub code-change request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("GitHub code-change service unavailable") from exc

    @staticmethod
    def _validate_path(path: str) -> str:
        path = str(path).strip().replace("\\", "/")
        if (not path or path.startswith("/") or ".." in path.split("/")
                or path.startswith(".git/") or path in {".env", ".env.example", "requirements.txt", "Procfile"}):
            raise ValueError("Chemin interdit pour une proposition de code")
        if not (path.startswith("nexus_services/") or path.startswith("docs/") or path in {"README.md"}):
            raise ValueError("Les propositions sont limitées à nexus_services/, docs/ et README.md")
        if path.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx")):
            raise ValueError("Les fichiers de données et secrets ne peuvent pas être modifiés par cette API")
        return path

    @staticmethod
    def _validate_content(content: str) -> str:
        content = str(content)
        if not content.strip() or len(content.encode("utf-8")) > 100_000:
            raise ValueError("Le contenu doit contenir 1 à 100 000 octets")
        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                raise ValueError("Le contenu ressemble à un secret; proposition refusée")
        return content

    def propose_file_change(
        self, *, path: str, content: str, title: str, summary: str,
    ) -> dict[str, Any]:
        config = code_change_status()
        if not config["configured"]:
            raise RuntimeError(
                "Configurer NEXUS_GITHUB_REPOSITORY et NEXUS_GITHUB_TOKEN pour ouvrir une pull request."
            )
        repository = os.environ["NEXUS_GITHUB_REPOSITORY"].strip()
        token = os.environ["NEXUS_GITHUB_TOKEN"].strip()
        base = config["base_branch"]
        safe_path = self._validate_path(path)
        safe_content = self._validate_content(content)
        title = str(title).strip()[:180]
        summary = str(summary).strip()[:4000]
        if not title or not summary:
            raise ValueError("Le titre et le résumé sont obligatoires")

        api = f"https://api.github.com/repos/{repository}"
        base_ref = self._request("GET", f"{api}/git/ref/heads/{base}", token)
        base_sha = base_ref.get("object", {}).get("sha")
        if not base_sha:
            raise RuntimeError("La branche de base n'a pas pu être résolue")
        proposal_branch = f"nexus-proposal-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self._request("POST", f"{api}/git/refs", token, {
            "ref": f"refs/heads/{proposal_branch}",
            "sha": base_sha,
        })

        file_url = f"{api}/contents/{safe_path}?ref={proposal_branch}"
        try:
            existing = self._request("GET", file_url, token)
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
            existing = {}
        file_sha = existing.get("sha")
        payload: dict[str, Any] = {
            "message": f"Nexus proposal: {title}",
            "content": base64.b64encode(safe_content.encode("utf-8")).decode("ascii"),
            "branch": proposal_branch,
        }
        if file_sha:
            payload["sha"] = file_sha
        self._request("PUT", f"{api}/contents/{safe_path}", token, payload)

        pr = self._request("POST", f"{api}/pulls", token, {
            "title": f"[Nexus proposal] {title}",
            "head": proposal_branch,
            "base": base,
            "body": (
                "## Nexus code-change proposal\\n\\n"
                f"{summary}\\n\\n"
                f"**File:** `{safe_path}`\\n"
                "**Execution:** this PR does not modify the running process.\\n"
                "**Safety:** wait for CI and human review; Nexus does not merge its own PR."
            ),
            "draft": True,
        })
        return {
            "status": "DRAFT_PR_CREATED",
            "repository": repository,
            "branch": proposal_branch,
            "path": safe_path,
            "pull_request_number": pr.get("number"),
            "pull_request_url": pr.get("html_url"),
            "merged": False,
            "requires_ci_and_human_review": True,
        }
