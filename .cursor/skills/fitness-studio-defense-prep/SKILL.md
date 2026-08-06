---
name: fitness-studio-defense-prep
description: Produces oral-defense questions, answers, follow-ups, and code-evidence prompts grounded in the fitness-studio repository and final2026.pdf. Use when preparing for the Zoom defense, rehearsing Flask, HTTP, MVC, SQLAlchemy, 3NF, workflows, BPA, RAG, Skills, cloud, or deployment questions.
---

# Fitness Studio Defense Preparation

## Evidence-first workflow

1. Read `final2026.pdf` and identify the rubric concepts relevant to the requested
   rehearsal.
2. Inspect the current code before drafting answers. Ground every project-specific
   statement in actual entrypoint, factory, controller, service, model,
   configuration, template, or test behavior.
3. Cover the implemented architecture accurately:
   - `app.py` is the local/Vercel WSGI entrypoint;
   - Flask-SQLAlchemy implements the model and persistence layer;
   - manager, member, and trainer are authenticated roles;
   - SQLite supports local development/tests and Supabase PostgreSQL supports
     production on Vercel;
   - Groq provides RAG/AI assistance with deterministic fallbacks;
   - runtime Python Skills are allow-listed tools under `skills/`;
   - Resend sends receipts when configured and otherwise uses a safe mock path.
   Explicitly distinguish Groq from the Ollama provider named in the course
   brief and explain it as the project's provider substitution.
4. Distinguish a user workflow from an organization-level business process.
5. Explain where authorization, validation, transactions, and database
   constraints each contribute; do not claim UI hiding provides security.
6. Include likely examiner follow-ups and concise recovery answers for uncertain
   or partially implemented areas.

## Output format

For each item provide:

- **Question**
- **Strong oral answer** in approximately 30-90 seconds
- **Code evidence** with repository paths and relevant symbols
- **Likely follow-up**
- **Short follow-up answer**

End with:

- a rapid-fire terminology round for Flask, HTTP/REST, MVC, PIV, SQL/3NF, BPA,
  RAG, cloud services, and Skills;
- a demo sequence mapped to rubric requirements;
- any claims the presenter should avoid because the code does not support them.

Never invent routes, tables, integrations, test results, or course requirements.
If code and documentation differ, state the difference and use current code as
the source for implementation behavior while using `final2026.pdf` for rubric
requirements.
