"""External API connectors (Jira, GitLab).

The concrete connector implementations live in ``app.jira`` and
``app.gitlab``. They are re-exported here under ``app.connectors`` so that
application code can depend on a stable, extensible connector namespace
(new connectors can be added here without touching call sites).
"""

from __future__ import annotations

from app.connectors.gitlab import GitLabConnector
from app.connectors.jira import JiraConnector

__all__ = ["GitLabConnector", "JiraConnector"]
