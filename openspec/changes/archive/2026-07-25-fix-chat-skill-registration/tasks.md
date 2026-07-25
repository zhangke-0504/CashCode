## 1. Skill Identity And Diagnostics

- [x] 1.1 Add bounded optional `display_name` parsing to `SkillManifest`, preserve canonical `name` validation, and expose fallback display names in catalog/content DTOs.
- [x] 1.2 Include `display_name` in Skill search indexing while keeping exact lookup, paths, conflicts, mentions, hashes, and snapshots keyed by canonical name.
- [x] 1.3 Replace raw `catalog.invalid` strings with bounded source/directory diagnostics that strip host paths and excessive exception detail without making invalid packages selectable.
- [x] 1.4 Add loader/catalog tests for localized display names, fallback labels, mutable display-name edits, identity mismatch rejection, diagnostic bounds, and valid-package isolation.

## 2. Shared Store And Cross-Root Ownership

- [x] 2.1 Centralize physical name-conflict detection across built-in, user, and Agent roots and apply it to managed create and ZIP import, including invalid and shadowed directories.
- [x] 2.2 Construct `SkillStore` alongside `SkillCatalog` in `SimpleAgentLoop`, expose both lifecycle-managed instances, and make FastAPI and `EvolutionService` reuse them instead of creating another store.
- [x] 2.3 Add store/lifespan tests proving API and Agent code receive the same instances, startup exposes no partial mutation service, and successful mutations advance one shared catalog revision.

## 3. Managed Chat Skill Authoring

- [x] 3.1 Implement `agent_skill_manage(action="create")` with canonical name, complete content, optional text support files, and bounded reason parameters while forcing enabled Agent ownership.
- [x] 3.2 Map validation, conflict, permission, and publication failures to bounded structured results and return `success=true` only after the shared catalog contains the expected Agent name/hash/source.
- [x] 3.3 Register the tool in the normal Agent registry after store initialization and update `skill-creator` plus Agent guidance to use it exclusively for explicit chat creation.
- [x] 3.4 Add protected-root checks to `write_file` and `edit_file` so direct user/Agent Skill mutations fail before filesystem changes while ordinary workspace writes remain compatible.
- [x] 3.5 Add focused tool tests for successful Agent creation, Chinese display names with ASCII slugs, invalid/mismatched names, cross-root conflicts, rollback cleanup, protected-root rejection, and path-free error payloads.

## 4. Skill Market And Composer Presentation

- [x] 4.1 Extend frontend Skill contracts and label helpers with `display_name`, using it for market/composer presentation while retaining canonical names in API routes and selection receipts.
- [x] 4.2 Render bounded invalid-package diagnostics in the Skill market as non-selectable error rows with deletion as the only action for invalid user/Agent packages.
- [x] 4.3 Add frontend tests for localized/fallback labels, canonical selection identity, invalid diagnostics, long error bounds, invalid deletion, and protected action gating.

## 5. Regression And Documentation

- [x] 5.1 Add a deterministic Agent-turn regression based on the recorded `认知扭曲` request that loads `skill-creator`, calls the managed tool, and never uses direct filesystem or shell-based registration.
- [x] 5.2 Verify the created `renzhi-niuqu` package is immediately returned as `source=agent`, displayed as `认知扭曲`, searchable/selectable by canonical identity, and editable from the Skill market without restart.
- [x] 5.3 Verify a failed managed creation produces no partial directory or false success and that the legacy invalid `data/skills/user/renzhi-niuqu` package is reported diagnostically but never auto-migrated or selected.
- [x] 5.4 Update README Skill authoring, canonical/display identity, invalid-diagnostic, ownership, and explicit legacy-package repair documentation.
- [ ] 5.5 Run the full server suite and client tests, lint, TypeScript compilation, production build, focused desktop/mobile market checks, `git diff --check`, and strict OpenSpec validation.

## 6. Invalid Package Deletion

- [x] 6.1 Add a guarded `SkillStore` operation and API route that identify invalid packages by source/directory, reject built-in, valid, missing, nested, or stale targets, and move confirmed invalid packages into recoverable snapshots before catalog refresh.
- [x] 6.2 Add server tests for user/Agent invalid deletion, built-in protection, valid-package race protection, traversal rejection, snapshot recovery data, refresh rollback, and immediate diagnostic removal.

## 7. Creator And Loader Alignment

- [x] 7.1 Update `skill-creator` with the exact CashCode canonical-name rule, supported frontmatter fields, localized display-name template, and managed validation retry contract.
- [x] 7.2 Add regressions proving the creator-generated localized package passes the current loader before publication, invalid content never creates a directory, and the historical direct-write flow is unavailable after restart.
- [x] 7.3 Update README invalid deletion/recovery and creation-validity guidance, then rerun the full automated validation suite.
