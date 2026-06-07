"""
Jira REST API v3 connector.

Handles:
- Issue listing by project/assignee/status
- Pagination (startAt / maxResults)
- Exponential backoff on rate limits (429) and transient errors (5xx)
- Ticket status normalisation to Tarzan's canonical status enum
- Issue reassignment
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import httpx

log = logging.getLogger(__name__)

# Jira status → Tarzan canonical
_STATUS_MAP: dict[str, str] = {
    "to do": "todo",
    "open": "todo",
    "backlog": "todo",
    "selected for development": "todo",
    "in progress": "in_progress",
    "in development": "in_progress",
    "in review": "in_review",
    "code review": "in_review",
    "blocked": "blocked",
    "impediment": "blocked",
    "done": "done",
    "closed": "done",
    "resolved": "done",
    "won't do": "cancelled",
    "wont do": "cancelled",
    "cancelled": "cancelled",
    "invalid": "cancelled",
}

_PRIORITY_MAP = {"highest": "critical", "high": "high", "medium": "medium",
                 "low": "low", "lowest": "low"}

PAGE_SIZE = 100
MAX_RETRIES = 5


def _canonical_status(jira_status: str) -> str:
    return _STATUS_MAP.get(jira_status.lower(), "in_progress")


def _canonical_priority(jira_priority: str) -> str:
    return _PRIORITY_MAP.get(jira_priority.lower(), "medium")


class JiraConnector:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self._base}/rest/api/3{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 10)) + attempt * 5
                    log.warning("Jira rate limited — waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    log.warning("Jira 5xx (%s) — retry in %ds", resp.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.TransportError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("Jira request failed after retries")

    async def _post(self, path: str, data: dict) -> Any:
        url = f"{self._base}/rest/api/3{path}"
        resp = await self._client.put(url, json=data)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def health_check(self) -> bool:
        try:
            await self._get("/myself")
            return True
        except Exception:
            return False

    async def iter_issues(
        self,
        project_keys: list[str],
        *,
        updated_after: Optional[datetime] = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield raw Jira issue dicts for the given projects."""
        jql_parts = [f"project in ({','.join(project_keys)})"]
        if updated_after:
            ts = updated_after.strftime("%Y-%m-%d %H:%M")
            jql_parts.append(f'updated >= "{ts}"')
        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

        start = 0
        while True:
            data = await self._get(
                "/search",
                params={
                    "jql": jql,
                    "startAt": start,
                    "maxResults": PAGE_SIZE,
                    "fields": "summary,description,status,priority,issuetype,"
                              "assignee,reporter,labels,created,updated",
                },
            )
            issues = data.get("issues", [])
            for issue in issues:
                yield issue
            start += len(issues)
            if start >= data.get("total", 0) or not issues:
                break

    def normalise_issue(self, raw: dict, base_url: str) -> dict:
        fields = raw.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        priority_name = (fields.get("priority") or {}).get("name", "medium")
        status_name = (fields.get("status") or {}).get("name", "")

        return {
            "external_id": raw["id"],
            "key": raw["key"],
            "project_key": raw["key"].rsplit("-", 1)[0],
            "summary": fields.get("summary", ""),
            "description": _extract_adf_text(fields.get("description")),
            "status": _canonical_status(status_name),
            "priority": _canonical_priority(priority_name),
            "issue_type": (fields.get("issuetype") or {}).get("name", "Task"),
            "reporter_username": assignee.get("accountId") or reporter.get("displayName"),
            "labels": fields.get("labels") or [],
            "jira_url": f"{base_url}/browse/{raw['key']}",
            "jira_created_at": _parse_dt(fields.get("created")),
            "jira_updated_at": _parse_dt(fields.get("updated")),
            "assignee_account_id": assignee.get("accountId"),
            "assignee_display_name": assignee.get("displayName"),
            "assignee_email": assignee.get("emailAddress"),
            "raw": str(raw),
        }

    async def reassign_issue(self, issue_key: str, assignee_username: str) -> None:
        """Reassign issue by accountId. Resolves username → accountId first."""
        users = await self._get("/user/search", {"query": assignee_username, "maxResults": 5})
        account_id = None
        for u in users:
            if u.get("displayName", "").lower() == assignee_username.lower():
                account_id = u["accountId"]
                break
        if not account_id and users:
            account_id = users[0]["accountId"]
        if not account_id:
            raise ValueError(f"Jira user not found: {assignee_username}")

        url = f"{self._base}/rest/api/3/issue/{issue_key}/assignee"
        resp = await self._client.put(url, json={"accountId": account_id})
        resp.raise_for_status()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_adf_text(doc: Optional[dict]) -> Optional[str]:
    """Recursively extract plain text from Jira's Atlassian Document Format."""
    if not doc:
        return None
    parts = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    return " ".join(parts).strip() or None