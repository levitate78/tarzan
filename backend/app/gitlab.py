"""
GitLab REST API connector.

Handles:
- Listing open merge requests with pagination
- Extracting Jira issue keys from MR title, description, and branch name
- Computing review age and breach flags
- Exponential backoff on rate limits / transient errors
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import httpx

log = logging.getLogger(__name__)

# Matches common Jira key patterns: PROJECT-123, ABC-4567
_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")

PAGE_SIZE = 50
MAX_RETRIES = 5


def extract_jira_keys(text: str) -> list[str]:
    """Return deduplicated Jira issue keys found in *text*."""
    return list(dict.fromkeys(_JIRA_KEY_RE.findall(text or "")))


class GitLabConnector:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            headers={
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict] = None) -> tuple[Any, dict]:
        """Return (body, response_headers)."""
        url = f"{self._base}/api/v4{path}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 10)) + attempt * 5
                    log.warning("GitLab rate limited — waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    log.warning("GitLab 5xx (%s) — retry in %ds", resp.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json(), dict(resp.headers)
            except httpx.TransportError:
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("GitLab request failed after retries")

    async def health_check(self) -> bool:
        try:
            await self._get("/user")
            return True
        except Exception:
            return False

    async def iter_mrs(
        self,
        project_id: int,
        *,
        state: str = "opened",
        updated_after: Optional[datetime] = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield raw GitLab MR dicts for *project_id*."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": PAGE_SIZE,
            "page": 1,
            "scope": "all",
        }
        if updated_after:
            params["updated_after"] = updated_after.isoformat()

        while True:
            body, headers = await self._get(f"/projects/{project_id}/merge_requests", params)
            for mr in body:
                yield mr
            next_page = headers.get("x-next-page")
            if not next_page:
                break
            params["page"] = int(next_page)

    async def get_project(self, project_id: int) -> dict:
        body, _ = await self._get(f"/projects/{project_id}")
        return body

    def normalise_mr(
        self,
        raw: dict,
        project_name: str,
        threshold_hours: float,
    ) -> dict:
        created_at = _parse_dt(raw.get("created_at"))
        now = datetime.now(timezone.utc)
        age_hours = (now - created_at).total_seconds() / 3600 if created_at else 0.0

        # Gather text blobs for Jira key extraction
        search_text = " ".join(filter(None, [
            raw.get("title", ""),
            raw.get("description", ""),
            raw.get("source_branch", ""),
        ]))
        jira_keys = extract_jira_keys(search_text)

        assignees = [a["username"] for a in (raw.get("assignees") or []) if a.get("username")]
        reviewers = [r["username"] for r in (raw.get("reviewers") or []) if r.get("username")]

        return {
            "external_id": raw["iid"],
            "project_id": raw["project_id"],
            "project_name": project_name,
            "title": raw.get("title", ""),
            "description": raw.get("description"),
            "state": raw.get("state", "opened"),
            "author_username": (raw.get("author") or {}).get("username"),
            "assignee_usernames": assignees,
            "reviewer_usernames": reviewers,
            "source_branch": raw.get("source_branch"),
            "target_branch": raw.get("target_branch"),
            "web_url": raw.get("web_url"),
            "jira_issue_keys": jira_keys,
            "review_age_hours": round(age_hours, 2),
            "breach_threshold_hours": threshold_hours,
            "breached": age_hours > threshold_hours,
            "mr_created_at": created_at,
            "mr_updated_at": _parse_dt(raw.get("updated_at")),
            "mr_merged_at": _parse_dt(raw.get("merged_at")),
        }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None