# Ponytail Audit — Fix Backlog

**Date:** 2026-07-05 · **Scope:** over-engineering only (delete/stdlib/native/yagni/shrink) ·
**Not covered:** correctness, security, performance (route those through `/code-review`).

## How this was produced

10 finder agents fanned out over disjoint subsystems (CLI, core generators,
flutter generators, utils, wizard, both stacks' templates, tests, packaging,
a cross-cutting dedup sweep), each required to grep the *whole* repo — including
Jinja templates and YAML config, since Python here is invoked from both — before
calling anything dead. 74 raw findings deduped to 74 unique. A 2-lens adversarial
verify pass (refs + replacement-viability) ran on all of them; the session token
limit killed 139 of 158 verifier agents partway through, so the un-verified half
was re-checked by hand (grep/AST-diff). Net: **48 confirmed**, **8 refuted**
outright, several resized down from the finder's first estimate.

`claude-arsenal` is not initialized in this repo — this is a plain markdown
backlog, not a queue. IDs are stable; check items off as you land them and note
the PR # inline.

---

## Before you cut: 2 findings are bugs wearing a ponytail costume

These looked like dead code to the finders but the *reason* they're unreachable
is a bug, not deliberate flexibility. Fix or decide on these before deleting —
don't just delete the dead branch and leave the underlying mismatch.

#### BUG-1 · `field.api_exclude_request` is guarded in templates but the schema doesn't have that key
The schema only defines `api_exclude_create` / `api_exclude_update` /
`api_exclude_response` (`schema/model.schema.json`). The guards at
`stacks/python-fastapi/templates/_shared/_tests.j2:9,92` and 6 more spots in
`tests/contract.py.j2` (lines 358, 630, 748, 1510, 1630, 1724) can never be
true — looks like a stale rename from `api_exclude_create`. **Decide:** is the
intent `api_exclude_create` (fix the guard) or was this meant to be a 4th
exclusion axis (add it to the schema)? Either way, don't just delete the dead
branches — figure out which key was meant first.

#### BUG-2 · `_scan_stacks()` scans a directory that doesn't exist
`wizard/actions/project_setup.py:16` scans
`Path(__file__).parent.parent / "stacks"` = `wizard/stacks/` — the real stacks
live at `src/model_generator/stacks/`, two levels up, not under `wizard/`. The
scan always finds nothing and silently falls back to `["python-fastapi"]`, so
the wizard has never actually offered the flutter stack. Fix the path
(`Path(__file__).parent.parent.parent / "stacks"`), then decide whether the
now-live scan result needs a test.

---

## P0 — biggest wins, low risk (do first)

#### CFG-1 · 8 dead declarative sections in `python-fastapi/config.yaml`
`types` (69-211, 143 lines), `api` (290-337, 48 lines), `constraints` (226-256,
31 lines), `naming` (338-355, 18 lines), `indexes` (257-273, 17 lines),
`relationships` (274-289, 16 lines), `timestamps` (212-225, 14 lines), `quality`
(365-371, 7 lines). Confirmed zero Python or template reader for any of these —
the type mapping is hardcoded in `model.py.j2` conditionals instead. Templates
only read `config.factory/paths/generation/auth`; Python reads
`paths/app/auth/project/dependencies/style/generation`.
**Fix:** delete all 8 blocks. *-294 lines.* Effort: S.

#### TOOL-1 · Two-script version-sync machinery (137 lines + Makefile + CI wiring)
`scripts/sync_version.py` + `scripts/check_version_sync.py`, `make version-sync`
/ `check-version-sync` targets, called from `lint` and both CI workflows.
**Fix:** `importlib.metadata.version("model-generator-kit")` in
`__init__.py.__version__` reads `pyproject.toml`'s version at import time with
zero sync step; drop the README-footer version line too. Needs the Makefile
and both `.github/workflows/*.yml` steps rewired in the same PR. *-140 lines.*
Effort: M (touches CI).

#### TEST-1 · 24 hand-rolled `os.getcwd()`/`chdir`/`try/finally` blocks
13× `tests/test_edge_cases.py`, 8× `tests/test_cli.py`, 2×
`tests/test_full_generation.py`, 1× `tests/test_integration.py`.
`tests/test_wizard.py` already uses `monkeypatch.chdir(tmp_path)` — same file,
better pattern, unused by its 24 siblings.
**Fix:** mechanical `monkeypatch.chdir(...)` swap, drop the try/finally.
*-96 lines.* Effort: S (mechanical, but touch 4 files — do as one PR).

---

## P1 — medium wins, batch by file

#### GEN-1 · Six near-identical bootstrap generators in `infrastructure.py:46-115`
`generate_base`, `generate_engine`, `generate_types`, `generate_database_init`,
`generate_errors`, `generate_validators` — same shape: resolve path → exists?
return None → render template → return dict.
**Fix:** table of `(path_key, default_path, template_name)` + one loop; keep
the public function names as thin `functools.partial`-style wrappers so
existing call sites and tests are untouched. *-40 lines.* Effort: M.

#### GEN-2 · `constraints.py`/`enums.py` duplicate their whole create/append branch
`generators/constraints.py:136-174` and `generators/enums.py:46-105` each
render the same template twice (mode="append" vs mode="create") with only the
`constraints=new_refs` vs `constraints=all_refs` argument differing.
**Fix:** compute the refs list + mode once, one render call. *-25 lines.*
Effort: M.

#### CONFTEST-1 · `generate_alt_fixture` is 63%-identical to `generate_fixture`
`utils/conftest_generator.py:361` (85 lines) vs `:480` (58 lines) — same
signature-build/docstring-emit/return shape, `alt_fixture_name = f"{base}_alt"`
is the only structural difference.
**Fix:** merge with an `alt: bool = False` flag. *-30 lines.* Effort: M.

#### TEST-2 · `project_env_with_python_root` fixture re-implements conftest's `_make_project_env`
`tests/stacks/python_fastapi/test_infrastructure.py:1026` (45 lines) duplicates
`conftest.py:30`'s `_make_project_env`, which already accepts an overrides dict.
**Fix:** `_make_project_env(tmp_path, {"python_root": ...})`. *-40 lines.*
Effort: S.

#### TEST-3 · Byte-identical 18-line `config` dict repeated 3× in `test_cli.py`
Lines 99, 156, 200 (a 4th at 323 differs — leave it).
**Fix:** module-level constant or fixture. *-36 lines.* Effort: S.

#### FLT-1 · `fields.py` DTO variants duplicate ~60% of the model variants
`collect_dto_imports` (38 lines) vs `collect_model_imports` (35 lines): 66%
line-identical. `resolve_dto_fields` (60 lines) vs `resolve_fields` (52 lines):
59% identical, including a verbatim 6-line enum-converter-name block.
**Fix:** extract the shared enum/import-collection chunk both call.
*-15 lines.* Effort: M.

#### TPL-1 · `_entity.j2` ships 4 macros, 3 unused
Only `get_primary_key_field` is ever imported (by `tests/contract.py.j2`);
`pluralize`, `to_kebab_case`, `to_snake_case`, `entity_display_name` have zero
importers anywhere.
**Fix:** delete the 3 unused macros. *-28 lines.* Effort: S.

#### QUAL-1 · `_run_ruff` is byte-identical to `_run_tool`
`utils/quality.py:74` — same params, same `subprocess.run` body, same warn
logic; only the docstring differs.
**Fix:** call `_run_tool` from `run_ruff_quality` instead. *-14 lines.*
Effort: S.

#### WIZ-1 · `_PATH_LAYOUTS["full-stack (backend/src/)"]` restates the stack default paths
`wizard/actions/project_setup.py:29` — key-for-key identical to
`config.yaml`'s own `paths` defaults.
**Fix:** emit nothing for the default layout entry (absence = tool default,
matches how the rest of this generator treats config). *-14 lines.* Effort: S.

#### TEST-4/5 · Duplicated test fixture data
`test_edge_cases.py:745` — same 19-line `config` dict appears twice (-17).
`test_enum_examples.py:21` — `_PATHS` is a byte-copy of `conftest.py`'s
`_PATHS` (-15). **Fix:** dedupe both. Effort: S each.

---

## P2 — small cuts, bundle into one cleanup PR

All ≤10 lines each; low individual risk, worth batching rather than one PR per item.

| ID | What | Where | Lines |
|----|------|-------|-------|
| GEN-3 | 3 pure-delegation `_v` wrappers (`_validate_auth_config_v` etc.) — no test patches them, unlike the 2 seams that stay | `generate.py:1077` | -8 |
| GEN-4 | `api_key_dependency_module()` — 9-line helper, 1 caller, wraps 1 path expr | `generators/infrastructure.py:603` | -8 |
| GEN-5 | `generate_main`/`generate_test_conftest_root` dual `domains`+`route_modules` "backward compat" params — 1 real caller | `generators/infrastructure.py:357` | -6 (⚠ published API — check downstream before touching) |
| GEN-6 | `_process_outputs` delegates verbatim to `write_outputs` | `generate.py:857` | -5 |
| GEN-7 | `'infrastructure'` appended to `targets_to_generate` — no stack registers that generator, guaranteed no-op | `generate.py:428` | -3 |
| GEN-8 | Dead `model_path: Path \| None = None` param, no caller passes it | `generators/api.py:194` | -2 |
| FLT-2 | `_entity_filename` defined twice (`generators.py:31`, `api.py:40`); `_api_enabled` defined twice (`api.py:45`, `cache.py:45`) | flutter/ | -7 |
| FLT-3 | `project_config` overlay param on 4 flutter infra generators — no caller ever passes an overlay | `generators/flutter/generators.py:190` | -8 |
| FLT-4 | `stack:` metadata dict ({name,description,version}) in both `config.yaml`s — `generate.py:408` explicitly ignores non-string values | both config.yaml | -8 |
| FLT-5 | Deferred in-function import "to avoid a circular import" that isn't real (api.py never imports generators.py) | `generators/flutter/generators.py:322` | -4 |
| FLT-6 | `naming:` config block — comment admits it's documentary only | `stacks/flutter/config.yaml:73` | -7 |
| FLT-7 | `types.integer` mapping — loader already aliases integer→counter before lookup | `stacks/flutter/config.yaml:119` | -3 |
| FLT-8 | `_ = GenContext` "re-export for symmetry" + its import — nothing imports it | `generators/flutter/__init__.py:206` | -3 |
| FLT-9 | Dead template kwargs: `package_name`→model.dart.j2, `entity_name`→request.dart.j2 (templates never read them) | `generators/flutter/generators.py:78`, `api.py:299` | -3 |
| FLT-10 | Hand-rolled `lib/` prefix strip | `generators/flutter/paths.py:50` | -2 (`str.removeprefix("lib/")`) |
| FLT-11 | `resolve_path`'s `default` kwarg (never supplied) + unused `camel_case` Jinja filter registration | `generators/flutter/paths.py:30`, `utils/templates.py:172` | -6 |
| CONST-1 | `constants.py` — 6-line module exporting 1 constant | `utils/constants.py` | -4 (fold `GENERATED_MARKER` into `utils/__init__.py`) |
| CONFTEST-2 | `topological_sort` + plumbing — fixture order pytest resolves by name anyway | `utils/conftest_generator.py:120` | -25 (⚠ changes generated conftest fixture order — verify against generated-output tests) |
| CONFTEST-3 | `needs_unique_suffix`'s `dep_mapping` param — passed by both callers, read by neither line of the body | `utils/conftest_generator.py:321` | -2 |
| QUAL-2 | `run_quality_tools` wrapper — body is just `(quality_runner or run_ruff_quality)(...)` | `utils/quality.py:234` | -8 |
| WIZ-2 | `_find_models_dir` — 6 lines for a 2-line existence check, 1 caller | `wizard/actions/generate.py:15` | -4 |
| VAL-1 | `--all` CLI flag on `model-val` — duplicates passing a directory; zero doc/test/CI use | `validate.py:212` | -6 (⚠ published CLI surface — note in CHANGELOG if cut) |
| VAL-2 | `load_schema`'s `exists()` + custom error + `sys.exit` guards a file that ships inside the package | `validate.py:31` | -3 |
| VAL-3 | `main()` re-opens/re-parses the model JSON with raw `json.load` just to count entities after `load_model` already parsed it | `validate.py:240` | -2 |
| SCHEMA-1 | `tests.field_validations` schema key — zero readers anywhere | `schema/model.schema.json:740` | -20 |
| TOOL-2 | Pytest markers `integration`/`unit`/`cli` declared, never applied (`slow` stays — it's used) | `pyproject.toml:102` | -3 |
| TOOL-3 | Unused dev dependency `pytest-cov` — nothing runs coverage | `pyproject.toml:37` | -1 line, -1 dep |
| TEST-6 | 5 tests use `tempfile.TemporaryDirectory()` context managers | `test_wizard.py:397` | -10 (`tmp_path` fixture) |
| TPL-2 | `_tests.j2` dead macro `format_test_financial` (imported, never called) + unused `section_divider` import + dead `reference_entity` fallback (key not in schema) | `_shared/_tests.j2:9,50`, `database/factory.py.j2:55` | -6 |

---

## Flagged, not recommended to cut yet

#### FLT-12 · 3 `JsonConverter` classes emitted into every generated project
`stacks/flutter/templates/infrastructure/converters.dart.j2:45` —
`DecimalConverter`/`BytesConverter`/`UtcDateTimeConverter`, kept per the
template's own comment "for any hand-written code that still uses the
class-annotation pattern." The top-level `fromJson`/`toJson` functions are the
actually-used path. This is speculative flexibility (-45 lines), but it's a
deliberate, documented product decision, not an oversight — cut only if you
want to drop that escape hatch for adopters.

---

## Refuted during verification (do not action)

The finders flagged these; adversarial verification killed them. Listed so
they don't get re-flagged next audit:

- Wizard plain-`input()` fallback in `prompts.py` — tested
  (`test_wizard.py:47`), deliberate support for base installs without the
  `[interactive]` extra.
- `{pkg}`/`resolve_path` "placeholder machinery" in `flutter/paths.py` — 20+
  live call sites across `generators.py`/`cache.py`/`api.py`.
- `flutter_secure_storage` conditional dependency — read at
  `generators/flutter/generators.py:217`.
- `generate_flutter_enums`'s unused `model` param — required by the uniform
  registry generator signature, all siblings take it too.
- Wizard `find_project_root()` "duplicating" `loaders.load_config` — the
  loader has no parent-directory walk; not the same logic.
- Stale `src/model_generator.egg-info/` — gitignored, never committed, not a
  repo artifact to clean up.

---

## Suggested PR batching

Following this repo's one-theme-per-PR convention (see the batch-N mutmut
arc in `next-session.md`):

1. **config purge:** CFG-1, FLT-4, FLT-6, FLT-7, TPL-2 (config.yaml + template dead-branch cleanup, no code logic changes)
2. **tooling hygiene:** TOOL-1, TOOL-2, TOOL-3 (touches CI — do alone)
3. **test suite dedup:** TEST-1 through TEST-6 (mechanical, safe to batch)
4. **infrastructure.py consolidation:** GEN-1, GEN-4, GEN-5 (⚠ check GEN-5 against any downstream import of `generate_main`)
5. **constraints/enums/conftest dedup:** GEN-2, CONFTEST-1, CONFTEST-2 (⚠ verify fixture order), CONFTEST-3, MIG item folded in
6. **generate.py wrapper removal:** GEN-3, GEN-6, GEN-7, VAL-1 (⚠ CHANGELOG), VAL-2, VAL-3
7. **flutter generator cleanup:** FLT-1, FLT-2, FLT-3, FLT-5, FLT-8, FLT-9, FLT-10, FLT-11
8. **wizard cleanup + BUG-2 fix:** BUG-2, WIZ-1, WIZ-2
9. **quality.py merge:** QUAL-1, QUAL-2
10. **schema/constants:** SCHEMA-1, CONST-1

BUG-1 (`api_exclude_request`) needs its own decision (fix the key vs. add the
schema field) before any of its dependent template cleanup lands — don't fold
it into batch 1.

**Total: -1045 lines, -1 dependency across 48 items.**
