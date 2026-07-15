"""Skill catalogue, member skills matrix, and team skills dashboard
(Requirements 2 and 3)."""

from __future__ import annotations

import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.common import profile_service, skills_service
from app.constants import LEVELS
from app.exceptions import ConflictError, NotFoundError, StorageError, ValidationError

logger = logging.getLogger(__name__)

skills_bp = Blueprint("skills", __name__)


@skills_bp.get("/catalogue")
@login_required
def catalogue():
    service = skills_service()
    skills = service.list_catalogue()
    reference_counts = {skill.id: service.reference_count(skill.id) for skill in skills}
    return render_template(
        "skills/catalogue.html", skills=skills, reference_counts=reference_counts
    )


@skills_bp.post("/catalogue")
@login_required
def add_skill():
    try:
        skill = skills_service().add_skill(request.form.get("name", ""))
    except (ValidationError, ConflictError, StorageError) as exc:
        flash(str(exc), "error")
    else:
        flash(f"Skill '{skill.name}' added to the catalogue.", "success")
    return redirect(url_for("skills.catalogue"))


@skills_bp.post("/catalogue/<int:skill_id>/remove")
@login_required
def remove_skill(skill_id: int):
    """Two-step removal: when the skill has matrix references, show a
    confirmation page with the reference count first (Requirement 2.8)."""
    service = skills_service()
    skill = service.get_skill(skill_id)
    if skill is None:
        flash("That skill does not exist in the catalogue.", "error")
        return redirect(url_for("skills.catalogue"))
    references = service.reference_count(skill_id)
    if references > 0 and request.form.get("confirmed") != "1":
        return render_template(
            "skills/confirm_remove.html", skill=skill, reference_count=references
        )
    try:
        result = service.remove_skill(skill_id)
    except (NotFoundError, StorageError) as exc:
        flash(str(exc), "error")
    else:
        if result.removed:
            flash(f"Skill '{result.skill_name}' removed from the catalogue.", "success")
        else:
            flash(
                f"Skill '{result.skill_name}' is referenced by "
                f"{result.reference_count} team member(s); it has been marked "
                "as deprecated and existing skills matrix entries were kept.",
                "info",
            )
    return redirect(url_for("skills.catalogue"))


@skills_bp.get("/dashboard")
@login_required
def dashboard():
    try:
        summary = skills_service().get_team_skills_summary()
    except StorageError:
        # Requirement 3.5: error message rather than a blank dashboard.
        flash("Could not load the latest skills data. Please try again.", "error")
        summary = None
    return render_template("skills/dashboard.html", summary=summary, levels=LEVELS)


@skills_bp.route("/matrix/<username>", methods=["GET", "POST"])
@login_required
def matrix(username: str):
    profile = profile_service().get_profile(username)
    if profile is None:
        abort(404)
    service = skills_service()
    if request.method == "POST":
        try:
            skill_id = int(request.form.get("skill_id", ""))
        except ValueError:
            flash("Choose a skill from the catalogue.", "error")
        else:
            try:
                service.assign_skill(
                    username,
                    skill_id,
                    request.form.get("current_level", ""),
                    request.form.get("aspiration_level") or None,
                )
            except (ValidationError, NotFoundError, StorageError) as exc:
                flash(str(exc), "error")
            else:
                flash("Skills matrix updated.", "success")
                return redirect(url_for("skills.matrix", username=username))
    entries = service.list_matrix(username)
    assigned_ids = {entry.skill_id for entry in entries}
    available_skills = [
        skill for skill in service.list_catalogue(include_deprecated=False)
    ]
    return render_template(
        "skills/matrix.html",
        profile=profile,
        entries=entries,
        available_skills=available_skills,
        assigned_ids=assigned_ids,
        levels=LEVELS,
    )


@skills_bp.post("/matrix/<username>/remove/<int:skill_id>")
@login_required
def remove_matrix_entry(username: str, skill_id: int):
    try:
        skills_service().remove_matrix_entry(username, skill_id)
    except (NotFoundError, StorageError) as exc:
        flash(str(exc), "error")
    else:
        flash("Skill removed from the skills matrix.", "success")
    return redirect(url_for("skills.matrix", username=username))
