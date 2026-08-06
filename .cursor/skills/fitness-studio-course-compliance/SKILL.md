---
name: fitness-studio-course-compliance
description: Reviews and guides fitness-studio architecture, refactors, documentation, and course-rubric work against the implemented repository and final2026.pdf. Use when changing MVC boundaries, persistence, Flask entrypoints, deployment, AI/cloud bonuses, or explaining course compliance.
---

# Fitness Studio Course Compliance

## Workflow

1. Read `final2026.pdf` for the authoritative course rubric.
2. Inspect the current implementation before making claims or proposing changes.
3. Separate course requirements from project implementation choices; the brief
   requires MVC and capabilities, not a specific repository filename layout.
4. Preserve working architecture unless the requested change explicitly replaces it:
   - `app.py` is the local and Vercel WSGI entrypoint.
   - `fitness_studio.create_app()` configures the Flask application.
   - Flask-SQLAlchemy models provide the persistence layer.
   - Controllers/blueprints authorize and orchestrate.
   - Services own multi-model business and integration workflows.
   - Jinja templates are the server-rendered views.
5. Preserve the supported database modes:
   - local development and tests use SQLite;
   - production on Vercel requires Supabase PostgreSQL through `DATABASE_URL`.
6. Check the three authenticated roles: manager, member, and trainer. Keep each
   role's workflows and authorization boundaries explicit.
7. Preserve and accurately describe the bonus integrations:
   - Groq-backed RAG and AI scheduling with local fallbacks;
   - Supabase PostgreSQL as the production cloud database;
   - allow-listed Flask runtime Python tools in `skills/`.
   State that the brief names Ollama while this implementation substitutes
   Groq; never claim the provider names are identical.
8. Treat Resend receipts as an external integration with a demo-safe fallback.
9. Verify claims against routes, models, services, configuration, and tests.
10. Report compliance as: requirement, implementation evidence, gap or risk, and
    the smallest safe correction.

## Guardrails

- Keep `app.py` as the sole WSGI entrypoint; do not add a competing entrypoint.
- Do not weaken controller authentication, role checks, or ownership checks.
- Do not describe the application as raw-SQL, no-ORM, SQLite-only, or
  trainer-unauthenticated.
- Do not prescribe exact filenames as if the course rubric mandates them.
- Keep `final2026.pdf` at the repository root.
- Keep deployment and local helper files unless a user explicitly changes scope.
- The Cursor IDE workflow skill does not replace the runtime Python skills in
  `skills/`; those remain application code invoked by Flask workflows.
