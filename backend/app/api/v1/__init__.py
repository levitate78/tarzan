"""API v1 router exports.

This module re-exports the router modules the application expects under
`app.api.v1` while keeping the implementations in their current files.
"""

from app import auth as auth
from app import issues as issues
from app import merge_requests as merge_requests
from app import dashboard as dashboard
from app.core import config as config
from app.models import users as users
from app.models import skills as skills

# Export names expected by app.main
__all__ = [
	"auth",
	"issues",
	"merge_requests",
	"dashboard",
	"config",
	"users",
	"skills",
]
