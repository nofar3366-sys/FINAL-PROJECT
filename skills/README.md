# Runtime Python Skills

This directory contains the application's allow-listed Flask runtime tools. These
Python functions expose narrowly scoped availability, member-status, and
scheduling operations to the AI workflows.

`registry.py` defines the callable allow-list and tool schemas. Authorization is
not delegated to a tool: the Flask controller must authenticate the caller,
enforce the required role or record ownership, and only then invoke a skill.
The skill functions still validate their domain inputs and reuse the same ORM
models and services as the rest of the application.

Current direct application usage includes:

- the authenticated member assistant calling the class-availability skill;
- the manager scheduling workflow calling the recurring-session skill after
  manager authorization and payload validation.

Other registered tools are available to explicitly authorized workflows and
automated tests.

These runtime Python skills are separate from the Cursor IDE workflow skills in
`.cursor/skills/`. Cursor skills guide an AI coding agent while it works on the
repository; they are not imported or executed by Flask and do not replace the
runtime tools in this directory.
