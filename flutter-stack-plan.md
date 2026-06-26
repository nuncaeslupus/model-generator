# Plan: Add a `flutter` Stack to model-generator

## Context

`model-generator` today ships exactly one stack — `python-fastapi` — that turns a
`*.model.json` spec into a FastAPI backend (SQLAlchemy models, Pydantic DTOs,
routes, pytest contract tests, Alembic migrations). The user wants a **second
stack that emits a Flutter (Dart) client** from the *same* specs, proving the
"one spec, many stacks" premise and giving mobile apps typed models + a typed
API client for free.

Two facts shape the design:

1. **Dart macros were cancelled (Jan 2025).** The 2026-standard codegen path is
   still `build_runner` + `freezed` + `json_serializable` + `retrofit`/`dio`. So
   our generator emits the **hand-authored annotated source** (`@freezed`
   classes, `@RestApi` retrofit clients); the user runs
   `dart run build_runner build` to produce the `.g.dart`/`.freezed.dart` files —
   exactly analogous to how the Python stack documents `ruff`/Alembic as
   post-gen steps.
2. **The engine core is already stack-agnostic; the orchestration layer is not.**
   `get_template_env`, `load_config`, the generator-function contract, and
   `_process_outputs` are generic. But `generate.py` hardcodes the Python
   generator set (dispatch table + target lists + `generate_infrastructure`),
   and `utils/quality.py` shells out to `ruff` specifically. That coupling is the
   real work.

**Decisions confirmed with the user:**
- **Engine:** introduce a **stack registry** (remove Python assumptions from
  shared code) rather than `if stack == "flutter"` branches.
- **Backend relationship:** generated client **consumes a FastAPI backend built
  from the same spec** (matching paths, pagination envelope, auth). Offline/local
  persistence is a **deferred Phase-4 cache layer**, designed-for but not built.
- **Money:** `financial`/`percentage` use the **`decimal` package, carried as
  JSON strings** — byte-compatible with the FastAPI wire format.

---

## Phase 0 — Engine generalization (prereq, Python behavior unchanged)

Introduce a lightweight **stack registry** so `generate.py` drives any stack
generically. Each stack module exposes a descriptor:

```python
# generators/<stack>/__init__.py
STACK = StackSpec(
    name=...,
    infrastructure_targets=[...],   # skip-if-exists
    domain_targets=[...],           # overwrite, per model file
    generators={target: fn, ...},   # fn(model, config, env, project_root)->dict|list|None
    infra_orchestrator=...,         # replaces hardcoded generate_infrastructure
    quality_runner=...,             # ruff (python) | dart format+analyze (flutter)
    cleanup_spec=...,               # path keys + glob patterns for --clean
    validators=[...],               # python: auth/base; flutter: none
)
```

Changes (all in **shared** code, regression-guarded by existing smoke jobs):
- `src/model_generator/generate.py` — replace module-level `GENERATORS`,
  `INFRASTRUCTURE_TARGETS`, `DOMAIN_TARGETS` (and the top-of-file generator
  imports) with `STACKS[args.stack]` lookups. Wrap the existing python-fastapi
  generators in a `StackSpec` (mechanical refactor, no behavior change). Defer
  `--target` validation out of `argparse` (the current static `choices=TARGETS`
  is python-only) — resolve the stack first, then validate `--target` against
  that stack's registered targets.
- Guard Python-only steps behind the registry: `_validate_paths_base`
  (`generate.py:578`, asserts `paths.base` is `…/base.py`), the auth validators
  + `_compute_auth_extra` in `_prepare_infra_modules` (`generate.py:926`), and
  the python-specific `--clean` path set. These become `StackSpec` fields, not
  inline assumptions.
- `src/model_generator/utils/quality.py` — generalize `run_quality_tools` to run
  `config.quality` commands (or the stack's `quality_runner`) instead of the
  hardcoded `_find_ruff`/`ruff`. Add a `dart`-locating helper mirroring
  `_find_ruff`, and **no-op gracefully when the SDK is absent** (generation must
  succeed without Flutter installed — mirrors the existing "ruff not found" warn).
  Note the formatter vs analyzer asymmetry: `dart format` accepts the generated
  file paths (like `ruff format`), but `dart analyze` must run on the **package
  root**, not individual files — it needs `pubspec.yaml`/`analysis_options.yaml`
  context to resolve imports. The `quality_runner` abstraction must allow a
  command to target the package root rather than the per-file list.
- `src/model_generator/utils/templates.py` — add a `camel_case` Jinja filter
  (sibling of the existing `snake_case`) to map snake_case spec keys → Dart
  camelCase fields.

---

## Phase 1 — Models, enums, converters, project scaffold

New stack dir `src/model_generator/stacks/flutter/` (`config.yaml` + `templates/`)
and generator package `src/model_generator/generators/flutter/`.

**`stacks/flutter/config.yaml`** (modeled on `stacks/python-fastapi/config.yaml`):
- `flutter.package_name` (drives `package:<pkg>/…` imports; default `app_api`,
  overridable in `.model-generator.yaml`).
- `dependencies`: runtime `freezed_annotation`, `json_annotation`, `dio`,
  `retrofit`, `decimal`; conditional `flutter_secure_storage` (auth);
  dev `build_runner`, `freezed`, `json_serializable`, `retrofit_generator`,
  `flutter_lints`.
- `paths` (Flutter `lib/` layout): `models: lib/<pkg>/models`,
  `enums: lib/<pkg>/models/enums.dart`, `api_client: lib/<pkg>/api`,
  `repositories: lib/<pkg>/repositories`, `api_core: lib/<pkg>/core`.
- `quality`: `formatter: "dart format ."`, `analyzer: "dart analyze"`.
- `types` (abstract → Dart):

| Abstract | Dart type | JSON handling |
|---|---|---|
| `uuid`, `reference`, `text`, `longtext` | `String` | plain + `@JsonKey(name:'<snake>')` |
| `financial`, `percentage` | `Decimal` | `@DecimalConverter()` ↔ JSON **string** |
| `counter`/`integer` | `int` | plain (`integer`→`counter` already normalized) |
| `boolean` | `bool` | plain |
| `datetime` | `DateTime` | `@UtcDateTimeConverter()` (ISO8601 + `Z`) |
| `binary` | `Uint8List` | `@BytesConverter()` (base64) |
| `enum` | `<EnumName>` | `@JsonValue('UPPER_CASE')` per constant |
| `json_object` | `Map<String,dynamic>` | plain |
| `json_array` | `List<{list_type}>` (default `dynamic`) | plain |

**Naming:** classes PascalCase (entity name as-is), Dart fields camelCase, wire
JSON stays snake_case via `@JsonKey(name:)`. Enum members UPPER_CASE — suppress
`constant_identifier_names` in `analysis_options.yaml`.
**Nullability:** `required && !api_exclude_response` → non-null; else nullable
(mirrors Python's `X | None`).

**Generators / templates / paths (Phase 1):**

| File | Generator fn | Template | Kind |
|---|---|---|---|
| `lib/<pkg>/models/<entity>.dart` (`@freezed`) | `generate_flutter_models` | `models/model.dart.j2` | domain |
| `lib/<pkg>/models/enums.dart` (UPPER_CASE + `@JsonValue`) | `generate_flutter_enums` | `models/enums.dart.j2` | domain |
| `lib/<pkg>/models/models_index.dart` (barrel) | `generate_flutter_models_index` | `models/index.dart.j2` | domain |
| `lib/<pkg>/core/converters.dart` (`Decimal`/`Bytes`/`UtcDateTime`) | `generate_converters` | `infrastructure/converters.dart.j2` | infra |
| `pubspec.yaml` (**pyproject analogue**, skip-if-exists) | `generate_pubspec` | `infrastructure/pubspec.yaml.j2` | infra |
| `analysis_options.yaml` | `generate_analysis_options` | `infrastructure/analysis_options.yaml.j2` | infra |
| `build.yaml` | `generate_build_yaml` | `infrastructure/build.yaml.j2` | infra |
| `README.md` (documents `dart run build_runner build`) | `generate_flutter_readme` | `infrastructure/README.md.j2` | infra |
| `.gitignore` (`.dart_tool/`, `build/`) | `generate_flutter_gitignore` | `infrastructure/gitignore.j2` | infra |

Reuse the existing shared loaders unchanged: `load_shared_enums`,
`load_shared_constraints`, `load_model`, `_normalize_field_types`. Reused spec
concepts: `entities`, `fields`, `type`, `required`, `default`, `list_type`, enum
defs, `api_field_name` (renames `@JsonKey`), `api_exclude_response`/`_create`/
`_update`, `mutability: immutable`. Constraints (min/max/pattern) → doc comments
only for now.

**build_runner:** document-only (pure file emitter). A future `--run-build`
opt-in can shell out, analogous to `run_quality_tools`.

---

## Phase 2 — Retrofit API client

| File | Generator fn | Template | Kind |
|---|---|---|---|
| `lib/<pkg>/api/<entity>_api.dart` (`@RestApi`) | `generate_flutter_api_client` | `api/retrofit_client.dart.j2` | domain |
| `lib/<pkg>/api/api_index.dart` (barrel) | `generate_flutter_api_index` | `api/index.dart.j2` | domain |
| `lib/<pkg>/core/pagination.dart` (`Paginated<T>` matching backend envelope) | `generate_flutter_pagination` | `infrastructure/pagination.dart.j2` | infra |
| `lib/<pkg>/core/api_client.dart` + `api_client_custom.dart` (dio base + baseUrl) | `generate_dio_setup` | `infrastructure/dio_setup.dart.j2` | infra (two-file) |
| `lib/<pkg>/core/auth_interceptor.dart` (conditional on `auth.strategy`) | `generate_auth_interceptor` | `infrastructure/auth_interceptor.dart.j2` | infra |

Driven by the spec's `api.enabled`, `api.prefix`, `api.endpoints`
(list→`@GET`, get→`@GET('/{id}')`, create→`@POST`, update→`@PUT/PATCH`,
delete→`@DELETE`), `api.pagination` (→ `Paginated<T>` vs `List<T>`), `api.filters`
(→ `@Query`). Generate separate `Create<E>Request`/`Update<E>Request` freezed
DTOs (this is what makes `api_exclude_create/update` meaningful; `immutable`
entities skip the update DTO — mirrors `generate_api_init`). Auth read coarsely:
`api-key`→`X-API-Key` header; `bcrypt-session`→cookie passthrough. Server-only
concepts (`auth` internals, `api.scope`, migrations, DB constraints) ignored.

Thin repository wrappers (`<entity>_repository.dart` overwrite +
`_repository_custom.dart` skip-if-exists) are the seam for Phase 4 — generate
stubs here so offline stays additive.

---

## Phase 3 — Example project + CI ("one spec, two stacks" proof)

- `examples/flutter-app/` reusing an existing spec (e.g. the catalog-api models)
  with `.model-generator.yaml: stack: flutter`.
- `scripts/smoke_generated_flutter.sh` (mirrors `smoke_generated_example.sh`):
  regenerate → `dart pub get` → `dart run build_runner build
  --delete-conflicting-outputs` (proves annotated source is codegen-valid) →
  `dart analyze` (zero errors) → optional `flutter test` round-trip.
- New CI job `generated-flutter` (via `subosito/flutter-action`), gated to PRs
  touching `stacks/flutter/**` **or the shared engine** (`src/model_generator/**`,
  e.g. `generate.py`, `utils/loaders.py`, `utils/templates.py`, `utils/quality.py`)
  — since the Phase-0 registry changes shared code, gating on `stacks/flutter/**`
  alone would miss engine regressions. Analogue of the existing `generated-example`
  job.
- Docs: stack `README.md`, `docs/user/` Flutter usage, update
  `docs/agent/template-extension-guide.md` and `status/next-session.md`.

---

## Phase 4 — Offline cache (shipped)

Drift/SQLite persistence behind the Phase-2 repository two-file pattern.
Freezed models are kept pure (no Drift annotations) — the cache layer is
purely additive and opt-in via `local_cache: true` in `.model-generator.yaml`.

Implemented generators (`generators/flutter/cache.py`):
- `generate_drift_tables` — one `Table` class per API-enabled entity (`lib/local/`)
- `generate_drift_database` — `AppDatabase` aggregator (`lib/core/local_database.dart`)
- `generate_cached_repositories` — cache-first repo subclass per entity (`lib/repositories/`)

Templates: `local/table.dart.j2`, `infrastructure/local_database.dart.j2`,
`repositories/cached_repository.dart.j2`.

The `flutter-app` example enables `local_cache: true`; the CI smoke job validates
the generated Drift source via `build_runner` + `dart analyze`.

---

## Cross-stack maintenance (the user's concern)

Stacks are independent by construction: each owns its `config.yaml` + `templates/`
+ generators. Backend-only features (new auth strategy, migration tweak) touch
**only** python-fastapi. The only forced cross-stack work is a **schema change**
(shared `model.schema.json` + loader normalization) — keep those additive. A new
abstract field type is opt-in per stack (each adds its own mapping). The Phase-0
registry removes the last Python assumptions from shared `generate.py`, so the
3rd/4th stack needs no shared-code edits.

---

## Critical files

- `src/model_generator/generate.py` — registry refactor; guard Python-only steps.
- `src/model_generator/utils/quality.py` — config-driven quality (ruff | dart).
- `src/model_generator/utils/templates.py` — add `camel_case` filter.
- `src/model_generator/utils/loaders.py` — verify no Python-only derivation fires
  for flutter (the `database_models`→`paths.base` block is already inert).
- `src/model_generator/stacks/flutter/config.yaml` + `templates/**` — new stack.
- `src/model_generator/generators/flutter/*.py` — new generators + `StackSpec`.
- `src/model_generator/stacks/python-fastapi/config.yaml` — reference only.

## Verification

1. **Unit (no Dart SDK, runs in `make test`):** `tests/test_flutter_generators.py`
   renders templates against fixture specs; assert emitted Dart has correct
   `@freezed`/`@RestApi`/`@JsonKey(name:'snake')`/`@JsonValue('UPPER')`, correct
   Dart types per the table, camelCase fields, and **no** hardcoded paths/imports/
   entity names (reuse the project-agnostic assertions in
   `docs/contributor/`).
2. **Regression:** existing python-fastapi smoke jobs must stay green after the
   Phase-0 refactor.
3. **Generated-Flutter smoke (Dart SDK in CI):** `scripts/smoke_generated_flutter.sh`
   — `pub get` → `build_runner build` → `dart analyze` (zero errors). Minimal
   viable gate = these three.
4. **Round-trip:** a generated test deserializes a known backend JSON payload
   (financial string, ISO datetime, base64 binary, UPPER_CASE enum) and
   re-serializes to byte-equality — proves wire compatibility with the FastAPI
   stack.
