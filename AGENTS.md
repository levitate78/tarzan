# AGENTS.md

# Project Overview

The project is a web application designed to interact with the GitLab and Jira APIs, providing dashboards of a teams current work items/merge requests, tracking work to identify when reviews are needed or support is required.

When making changes, prefer minimal, targeted modifications over broad refactors.
---

# Development Principles

## General

- Understand the existing implementation before modifying it.
- Preserve existing behavior unless the task explicitly requires changing it.
- Do not rewrite working code without a clear reason.
- Prefer consistency with existing patterns over introducing new frameworks or styles.
- Avoid speculative improvements.
- Keep pull requests focused on the requested task.
- Ensure any changes work across deployment architectures including Docker Compose and Kubernetes.

## Code Quality

- Prioritize readability over cleverness.
- Use descriptive variable and function names.
- Avoid excessive abstraction.
- Remove dead code when encountered.
- Avoid introducing global state.

# HTML Guidelines

## Templates

- Preserve existing template structure.
- Reuse existing components and partials.
- Keep markup semantic.

Use:

- header
- nav
- main
- section
- article
- footer

when appropriate.

## Accessibility

Maintain accessibility standards:

- Use proper labels.
- Use semantic elements.
- Ensure keyboard accessibility.
- Preserve ARIA attributes.
- Preserve alt text.

---

# CSS Guidelines

## Styling

- Follow existing CSS architecture.
- Reuse existing utility classes.
- Avoid inline styles.

## Changes

- Make the smallest styling change necessary.
- Do not introduce new design systems.
- Do not change spacing, typography, or colors globally unless requested.

## Responsive Design

Ensure changes work on:

- Mobile
- Tablet
- Desktop

---

# JavaScript Guidelines

## General

- Prefer modern JavaScript.
- Avoid introducing frameworks unless already used.
- Use existing project conventions.

## DOM Manipulation

- Minimize unnecessary DOM updates.
- Avoid duplicate event listeners.
- Clean up listeners when appropriate.

## Network Requests

- Reuse existing API helpers.
- Handle loading and error states.
- Validate responses.

---

# Security Requirements

- ALWAYS highlight any identified security vulnerabilities, and propose fixes to resolve issues.
- NEVER introduce known or potential vulnerabilities into the codebase.

## Never

- Expose secrets.
- Hardcode credentials.
- Log passwords.
- Log authentication tokens.
- Disable security checks.

## Input Validation

Treat all user input as untrusted.

Validate:

- Query parameters
- Form inputs
- JSON payloads
- Uploaded files

## Authentication

Preserve existing authentication and authorization behavior unless explicitly requested.

---

# Database Rules

If database migrations are required:

- Generate only the migration necessary for the requested change.
- Do not modify historical migrations.
- Preserve backward compatibility where possible.

Avoid:

- Destructive schema changes
- Large data migrations

unless explicitly requested.

---

# API Changes

When modifying APIs:

- Maintain backwards compatibility whenever possible.
- Update tests.
- Update documentation.
- Preserve response formats.

---

# Testing Requirements

After making changes:

1. Run relevant tests.
2. Run linting.
3. Verify no obvious regressions.

---

# Documentation

Update documentation when:

- Behavior changes
- APIs change
- Configuration changes
- New environment variables are added

Relevant files:

- README.md
- docs/

---

# Git Guidelines

Keep commits focused.

Avoid:

- Unrelated formatting changes
- Repository-wide refactors
- Renaming files unnecessarily

---

# Decision Priority

When instructions conflict, follow this order:

1. Direct user request
2. More specific AGENTS.md instructions
3. Repository conventions
4. General best practices

---

# Expected Agent Behaviour

Before making changes:

1. Read only files relevant to the task.
2. Understand the current implementation.
3. Identify the smallest safe change.
4. Update tests if needed.
5. Verify consistency with surrounding code.

When uncertain:

- Ask for clarification rather than guessing.

Prefer correctness over speed.
Prefer minimal changes over large refactors.
