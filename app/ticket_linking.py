"""Jira ticket reference extraction from merge request text (Requirement 7).

A Ticket_Reference is one or more uppercase letters, a hyphen, and one to six
decimal digits (e.g. ``ABC-123``), where the letter prefix matches a
configured Jira project key.
"""

from __future__ import annotations

import re

# Guards prevent partial matches inside longer identifiers:
# - no uppercase letter immediately before (so "XABC-1" matches as "XABC-1",
#   not "ABC-1")
# - no digit immediately after (so "ABC-1234567" is not a valid reference)
_TICKET_PATTERN = re.compile(r"(?<![A-Z])([A-Z]+)-([0-9]{1,6})(?![0-9])")


def extract_ticket_references(text: str | None, project_keys: set[str]) -> set[str]:
    """Return the set of distinct ticket references in ``text`` whose prefix
    is a configured Jira project key. No matches → empty set, never an error."""
    if not text or not project_keys:
        return set()
    references = set()
    for match in _TICKET_PATTERN.finditer(text):
        if match.group(1) in project_keys:
            references.add(match.group(0))
    return references
