"""Thin wrapper around `python-gitlab`.

Handles authentication, pagination, and timeouts, raising the typed
GitLabClientError. Returned values are plain dicts with normalised fields.
"""

from __future__ import annotations

import logging

from app.exceptions import GitLabClientError

logger = logging.getLogger(__name__)


class GitLabClient:
    def __init__(self, url: str, token: str, timeout_seconds: int = 10):
        self._url = url.rstrip("/")
        try:
            import gitlab

            self._gitlab = gitlab.Gitlab(
                self._url, private_token=token, timeout=timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001
            raise GitLabClientError(
                f"Could not connect to GitLab: {type(exc).__name__}"
            ) from exc

    def list_merge_requests(self, project_id: int, state: str = "opened") -> list[dict]:
        try:
            project = self._gitlab.projects.get(project_id, lazy=True)
            merge_requests = project.mergerequests.list(
                state=state, iterator=True, per_page=50
            )
            return [self._normalise_mr(mr, project_id) for mr in merge_requests]
        except GitLabClientError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GitLabClientError(
                f"GitLab merge request fetch failed for project {project_id}: "
                f"{type(exc).__name__}"
            ) from exc

    def _normalise_mr(self, mr, project_id: int) -> dict:
        reviewers = [
            reviewer.get("username", "")
            for reviewer in (getattr(mr, "reviewers", None) or [])
            if isinstance(reviewer, dict)
        ]
        return {
            "id": mr.id,
            "iid": getattr(mr, "iid", None),
            "project_id": project_id,
            "title": getattr(mr, "title", "") or "",
            "author_username": (getattr(mr, "author", None) or {}).get("username"),
            "source_branch": getattr(mr, "source_branch", None),
            "target_branch": getattr(mr, "target_branch", None),
            "description": getattr(mr, "description", "") or "",
            "created_at": getattr(mr, "created_at", None),
            "web_url": getattr(mr, "web_url", None),
            "reviewers": reviewers,
            "review_status": self._review_status(mr),
        }

    @staticmethod
    def _review_status(mr) -> str:
        """Map GitLab review state onto Awaiting Review / Changes Requested /
        Approved (Requirement 6.3)."""
        try:
            reviewer_states = {
                reviewer.get("state", "")
                for reviewer in (getattr(mr, "reviewers", None) or [])
                if isinstance(reviewer, dict)
            }
            if "requested_changes" in reviewer_states:
                return "Changes Requested"
            approvals = mr.approvals.get()
            if getattr(approvals, "approved", False):
                return "Approved"
        except Exception:  # noqa: BLE001 - approval data is best-effort
            pass
        return "Awaiting Review"
