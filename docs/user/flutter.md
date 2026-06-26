# Flutter Stack

Generate a typed Dart/Flutter client from the same JSON spec that drives your FastAPI backend. One spec, two stacks.

---

## Overview

The `flutter` stack reads the same `*.model.json` specification files as the `python-fastapi` stack and emits:

- `@freezed` data classes for every entity
- `@JsonValue`-annotated enums
- `@RestApi` retrofit clients for every API-enabled entity
- Request DTOs (`Create<Entity>Request`, `Update<Entity>Request`)
- Repository wrappers with a `_custom.dart` seam for offline overrides
- Project scaffold: `pubspec.yaml`, `analysis_options.yaml`, `build.yaml`, converters, Dio setup, pagination, and a conditional auth interceptor

The generated client is wire-compatible with a FastAPI backend built from the same spec: matching field names, pagination envelope, decimal-as-string encoding, and auth strategy.

Set `local_cache: true` in `.model-generator.yaml` to add an optional Drift/SQLite offline-cache layer: Drift table classes, an `AppDatabase` aggregator, and cache-first repository subclasses that read from SQLite when available and fall back to the network.

---

## Prerequisites

- Flutter SDK 3.4 or later (includes Dart 3.3+)
- `model-generator-kit` installed — see the [Installation Guide](./installation.md)
- Dart packages added to `pubspec.yaml` (the generator emits the dependency list; run `dart pub get` once to install them)

---

## Quick Start

### Step 1 — set the stack in `.model-generator.yaml`

```yaml
project:
  name: "My App"

stack: flutter

flutter:
  package_name: my_api   # drives lib/my_api/… and package:my_api/… imports
```

### Step 2 — generate

```bash
cd your-project
model-gen models/ --target all
```

### Step 3 — install Dart dependencies and run code generation

```bash
dart pub get
dart run build_runner build --delete-conflicting-outputs
```

`build_runner` produces the `.freezed.dart` and `.g.dart` files that the annotated source references. This step is required before the generated client compiles.

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `stack` | — | Set to `flutter` to select this stack (required) |
| `flutter.package_name` | `app_api` | Dart package name; drives `lib/<name>/` layout and `package:<name>/` imports |
| `auth.strategy` | — | `api-key` or `bcrypt-session`; omit for unauthenticated APIs |
| `auth.key_env` | `API_KEY` | Environment variable holding the shared secret (`api-key` strategy only) |
| `auth.header_name` | `X-API-Key` | HTTP header name the client sends (`api-key` strategy only) |
| `local_cache` | `false` | Set to `true` to generate the Drift/SQLite offline cache layer (see [Offline Cache](#offline-cache-phase-4)) |

Example with api-key auth:

```yaml
project:
  name: "Catalog API Client"

stack: flutter

flutter:
  package_name: catalog_api

auth:
  strategy: api-key
  key_env: CATALOG_API_KEY
  header_name: X-Catalog-Key
```

---

## Generated File Layout

With `package_name: my_api`, the generator writes:

```
lib/my_api/
├── models/
│   ├── enums.dart              # shared enums (@JsonValue per constant)
│   ├── models_index.dart       # barrel re-export
│   ├── <entity>.dart           # @freezed data class per entity
│   └── <entity>_requests.dart  # Create<Entity>Request, Update<Entity>Request
├── api/
│   ├── <entity>_api.dart       # @RestApi retrofit client per entity
│   └── api_index.dart          # barrel re-export
├── repositories/
│   ├── <entity>_repository.dart               # thin wrapper (generated, overwrite)
│   ├── <entity>_repository_custom.dart        # your seam (skip-if-exists)
│   └── <entity>_cached_repository.dart        # cache-first subclass (local_cache: true)
├── local/                                     # local_cache: true only
│   └── <entity>_table.dart                    # Drift Table class per entity
└── core/
    ├── converters.dart          # DecimalConverter, UtcDateTimeConverter, BytesConverter
    ├── pagination.dart          # Paginated<T> matching the backend envelope
    ├── api_client.dart          # Dio base configuration
    ├── api_client_custom.dart   # baseUrl / interceptor wiring (skip-if-exists)
    ├── auth_interceptor.dart    # conditional on auth.strategy
    └── local_database.dart      # Drift AppDatabase aggregator (local_cache: true)
```

Root-level scaffold files (skip-if-exists):

```
pubspec.yaml
analysis_options.yaml
build.yaml
.gitignore
README.md
```

---

## Post-Generation Steps

After running `model-gen`, two steps are required before the generated code compiles:

```bash
# 1. Install runtime and dev dependencies declared in the generated pubspec.yaml
dart pub get

# 2. Run build_runner to produce .freezed.dart and .g.dart files
dart run build_runner build --delete-conflicting-outputs
```

The `--delete-conflicting-outputs` flag removes stale generated parts from a previous build. Omit it on the first run if you prefer an explicit prompt.

To watch for changes during development:

```bash
dart run build_runner watch --delete-conflicting-outputs
```

---

## Type Mapping

Every abstract field type from the JSON spec maps to a concrete Dart type:

| Abstract type | Dart type | Wire format / converter |
|---|---|---|
| `uuid` | `String` | plain string + `@JsonKey(name: 'snake_field')` |
| `reference` | `String` | plain string + `@JsonKey(name: 'snake_field')` |
| `text` | `String` | plain string + `@JsonKey(name: 'snake_field')` |
| `longtext` | `String` | plain string + `@JsonKey(name: 'snake_field')` |
| `financial` | `Decimal` | JSON string ↔ `Decimal` via `@DecimalConverter()` |
| `percentage` | `Decimal` | JSON string ↔ `Decimal` via `@DecimalConverter()` |
| `counter` | `int` | plain integer |
| `integer` | `int` | plain integer (`integer` is an alias for `counter`) |
| `boolean` | `bool` | plain boolean |
| `datetime` | `DateTime` | ISO8601 + trailing `Z` via `@UtcDateTimeConverter()` |
| `binary` | `Uint8List` | base64 string ↔ bytes via `@BytesConverter()` |
| `enum` | `<EnumName>` | `@JsonValue('UPPER_CASE')` per constant |
| `json_object` | `Map<String, dynamic>` | plain object |
| `json_array` | `List<{list_type}>` | plain array; `list_type` defaults to `dynamic` |

**Decimal fields** use the `decimal` package (`package:decimal/decimal.dart`). The wire format is a JSON string, which is byte-compatible with the `Numeric` type the FastAPI stack emits.

**Enum values** are always UPPER_CASE on the wire (matching the Python stack), decorated with `@JsonValue('UPPER_CASE')` on each constant. The `analysis_options.yaml` suppresses `constant_identifier_names` so Dart's linter does not flag the uppercase members.

**Nullable fields** — any field that is not `required: true` in the spec is emitted as a nullable Dart type (e.g. `String?`).

---

## Auth Strategies

The Flutter stack reads the same `auth.strategy` you set for the Python backend and generates a matching client-side interceptor.

### `api-key`

Generates `core/auth_interceptor.dart` with an `AuthInterceptor` that injects the configured header on every request:

```dart
// Excerpt from generated auth_interceptor.dart
class AuthInterceptor extends Interceptor {
  final String apiKey;
  const AuthInterceptor(this.apiKey);

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['X-Catalog-Key'] = apiKey;
    super.onRequest(options, handler);
  }
}
```

Wire the interceptor from `core/api_client_custom.dart` (skip-if-exists, yours to edit).

### `bcrypt-session`

Generates `core/auth_interceptor.dart` with an `AuthInterceptor` that passes the session cookie through and adds the CSRF double-submit token to mutating requests. Cookie storage uses `flutter_secure_storage` (added automatically to `pubspec.yaml` when this strategy is active).

---

## Wire Compatibility

The generated Flutter client is wire-compatible with a FastAPI backend produced from the same spec:

- Field names on the wire are `snake_case` (Python) ↔ `@JsonKey(name: 'snake_field')` (Dart camelCase member).
- Decimal values travel as JSON strings in both directions.
- Datetime values use ISO8601 with a trailing `Z` (UTC) in both directions.
- Binary values use base64 in both directions.
- Enum values are UPPER_CASE strings in both directions.
- The pagination envelope (`items`, `total`, `page`, `page_size`) matches the `Paginated<T>` class in `core/pagination.dart`.
- Auth headers / cookies match what the generated FastAPI dependency expects.

If you change the spec, regenerate both stacks from the same source to keep them in sync.

---

## Example

`examples/flutter-app/` is the bundled "one spec, two stacks" proof. It uses the same catalog-api spec (`catalog.model.json` + `_shared/enums.json`) as `examples/catalog-api/`, configured for the Flutter stack:

```yaml
# examples/flutter-app/.model-generator.yaml
stack: flutter

flutter:
  package_name: catalog_api

auth:
  strategy: api-key
  key_env: CATALOG_API_KEY
  header_name: X-Catalog-Key

local_cache: true
```

The example exercises: `@freezed` models, the `ProductStatus` enum with `@JsonValue`, `@RestApi` clients for Category (public) and Product (auth-gated), `DecimalConverter` on the `price` field, `AuthInterceptor` adding `X-Catalog-Key`, repository wrappers, Dio setup, pagination, and the full Phase 4 offline-cache layer (Drift tables, `AppDatabase`, cached repositories).

To regenerate it:

```bash
cd examples/flutter-app
model-gen models/ --target all
dart pub get
dart run build_runner build --delete-conflicting-outputs
dart analyze
```

The `make smoke-flutter` target in the project root runs this sequence against a clean temporary tree and checks that `dart analyze` reports zero errors.

---

## Offline Cache (Phase 4)

Set `local_cache: true` in `.model-generator.yaml` to activate the Drift/SQLite offline cache layer. The generator adds three file types per API-enabled entity:

| File | Kind | What it does |
|------|------|--------------|
| `lib/local/<entity>_table.dart` | overwrite | Drift `Table` class mirroring the spec fields |
| `lib/core/local_database.dart` | overwrite | `@DriftDatabase` aggregator updated across model files |
| `lib/repositories/<entity>_cached_repository.dart` | overwrite | Cache-first subclass of the base repository |

**Cache strategy per operation:**

| Operation | Strategy |
|-----------|----------|
| `list()` (unpaginated, unfiltered) | Cache-first: returns local rows when populated; fetches network on miss and populates cache |
| `list()` (paginated or filtered) | Network-only: per-page/per-filter cache keying is out of scope |
| `getById()` | Cache-first: returns cached row when present; fetches network and stores on miss |
| `create()` / `update()` | Write-through: network first, then upsert the result into the cache |
| `delete()` | Write-through: network first, then remove from cache |

**To activate per entity**, update `<entity>_repository_custom.dart` to extend the cached class and pass an `AppDatabase`:

```dart
// <entity>_repository_custom.dart (yours to edit — skip-if-exists)
class CategoryRepositoryCustom extends CategoryCachedRepository {
  CategoryRepositoryCustom(super.client, AppDatabase db) : super(db);
}
```

Then inject `AppDatabase` wherever you create the repository (e.g. in your DI container). Entities that don't need offline reads can keep their `_custom.dart` extending the plain base class.

**Dependencies** — when `local_cache: true`, the generated `pubspec.yaml` includes:

```yaml
dependencies:
  drift: any
  drift_flutter: any
  sqlite3_flutter_libs: any

dev_dependencies:
  drift_dev: any
```

Run `dart pub get` and `dart run build_runner build --delete-conflicting-outputs` after generation to resolve packages and produce Drift's generated files (`local_database.g.dart`, etc.).

---

## Not Yet Implemented

- **`dart run build_runner` invoked by the generator** — the generator is a pure file emitter. A future `--run-build` flag could shell out to `build_runner`, analogous to `run_quality_tools` in the Python stack. For now, run it manually as described above.
