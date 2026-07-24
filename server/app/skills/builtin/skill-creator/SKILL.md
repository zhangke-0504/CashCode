---
name: skill-creator
description: Design valid CashCode Skills with concise instructions and progressively loaded scripts, references, templates, and assets.
version: 1
tags: [skill, workflow, authoring]
triggers: [create a skill, update a skill, reusable workflow]
requires:
  tools: []
---

# CashCode Skill Creator Contract

Create broad reusable workflow packages, not one-turn notes.

Required package shape:

```text
<slug>/
  SKILL.md
  references/   optional detailed knowledge
  templates/    optional editable starters
  scripts/      optional deterministic helpers
  assets/       optional output resources
```

Rules:

1. Use a lowercase slug matching frontmatter `name`.
2. Write a plain string `description` containing both capability and trigger intent.
3. Keep `SKILL.md` concise: trigger conditions, ordered steps, pitfalls, and verification.
4. Move detailed variants into directly linked supporting files.
5. Declare required and optional tools, MCP servers, binaries, and environment variables structurally.
6. Loading a Skill never authorizes executing its scripts.
7. Use the Skill management API for mutations so validation, hashes, snapshots, and catalog refresh occur.
8. Built-in Skills are read-only. Evolution may modify only agent-created Skills and requires proposal approval.

Validate every package before enabling it. Test scripts explicitly when a Skill introduces them.
