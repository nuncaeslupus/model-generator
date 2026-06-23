"""Tests for the Flutter (Dart) stack API layer — Phase 2.

Renders the Phase-2 templates against fixture specs and asserts the emitted Dart
is correct (``@RestApi`` clients, the right HTTP verbs/paths, ``Paginated<T>`` vs
``List<T>`` per ``api.pagination``, ``@Query`` filters, Create/Update DTO
presence/exclusion, the conditional auth interceptor) AND project-agnostic (no
hardcoded entity names, paths, or package names leak into the templates).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.generators.flutter import (
    FLUTTER_STACK,
    generate_auth_interceptor,
    generate_dio_setup,
    generate_flutter_api_client,
    generate_flutter_api_index,
    generate_flutter_pagination,
    generate_flutter_repositories,
    generate_flutter_request_dtos,
)
from model_generator.generators.flutter.fields import (
    resolve_dto_fields,
)
from model_generator.utils.templates import get_template_env

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_STACK_CONFIG_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "model_generator"
    / "stacks"
    / "flutter"
    / "config.yaml"
)


@pytest.fixture
def flutter_config() -> dict[str, Any]:
    with _STACK_CONFIG_PATH.open(encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    return config


@pytest.fixture
def env() -> Any:
    return get_template_env("flutter")


@pytest.fixture
def model() -> dict[str, Any]:
    """Multi-entity fixture exercising every Phase-2 path.

    * ``Widget``    — full CRUD, paginated, owner-scoped, with filters.
    * ``Ledger``    — immutable (no Update DTO / update endpoint).
    * ``Note``      — list/get only (no DTOs), not paginated.
    * ``Secret``    — ``api.enabled: false`` (no client at all).
    """
    return {
        "domain": "catalog",
        "entities": {
            "Widget": {
                "table": "widgets",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "owner_id": {"type": "reference", "required": True},
                    "display_name": {"type": "text", "required": True},
                    "unit_price": {"type": "financial", "required": True},
                    "status": {
                        "type": "enum",
                        "enum_name": "WidgetStatus",
                        "required": True,
                    },
                    "internal_note": {
                        "type": "text",
                        "api_exclude_create": True,
                        "api_exclude_update": True,
                    },
                },
                "api": {
                    "enabled": True,
                    "prefix": "widgets",
                    "scope": {"owner_field": "owner_id"},
                    "endpoints": ["list", "create", "get", "update", "delete"],
                    "pagination": True,
                    "filters": ["status"],
                },
            },
            "Ledger": {
                "table": "ledgers",
                "mutability": "immutable",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "amount": {"type": "financial", "required": True},
                },
                "api": {
                    "enabled": True,
                    "prefix": "ledgers",
                    "endpoints": ["list", "create", "get", "update"],
                    "pagination": True,
                },
            },
            "Note": {
                "table": "notes",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "body": {"type": "text"},
                },
                "api": {
                    "enabled": True,
                    "prefix": "notes",
                    "endpoints": ["list", "get"],
                    "pagination": False,
                },
            },
            "Secret": {
                "table": "secrets",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                },
                "api": {"enabled": False},
            },
        },
    }


def _clients(
    model: dict[str, Any], config: dict[str, Any], env: Any, tmp_path: Path
) -> dict[str, str]:
    """Render the api clients keyed by entity stem -> content."""
    outputs = generate_flutter_api_client(model, config, env, tmp_path)
    return {Path(o["path"]).name: str(o["content"]) for o in outputs}


# --------------------------------------------------------------------------- #
# Stack registration (Phase 2 additions)
# --------------------------------------------------------------------------- #


class TestPhase2Registration:
    def test_domain_targets_added(self) -> None:
        for target in ("requests", "api-client", "api-index", "repositories"):
            assert target in FLUTTER_STACK.domain_targets
            assert target in FLUTTER_STACK.generators

    def test_infra_targets_added(self) -> None:
        for target in ("pagination", "dio-setup", "auth-interceptor"):
            assert target in FLUTTER_STACK.infrastructure_targets
            # Infra targets are emitted by the orchestrator, not the dispatch dict.
            assert target not in FLUTTER_STACK.generators

    def test_cleanup_covers_api_and_repositories(self) -> None:
        keys = FLUTTER_STACK.cleanup_spec.source_path_keys
        assert "api_client" in keys
        assert "repositories" in keys


# --------------------------------------------------------------------------- #
# Retrofit client
# --------------------------------------------------------------------------- #


class TestRetrofitClient:
    def test_restapi_class_and_factory(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        clients = _clients(model, flutter_config, env, tmp_path)
        content = clients["widget_api.dart"]
        assert "@RestApi()" in content
        assert "abstract class WidgetApi {" in content
        assert "factory WidgetApi(Dio dio, {String? baseUrl}) = _WidgetApi;" in content

    def test_http_verbs_and_paths(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _clients(model, flutter_config, env, tmp_path)["widget_api.dart"]
        assert "@GET('/widgets')" in content
        assert "@POST('/widgets')" in content
        assert "@GET('/widgets/{id}')" in content
        assert "@PUT('/widgets/{id}')" in content
        assert "@DELETE('/widgets/{id}')" in content
        assert "@Path('id') String id" in content
        assert "@Body() CreateWidgetRequest body" in content
        assert "@Body() UpdateWidgetRequest body" in content

    def test_pagination_return_type(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        clients = _clients(model, flutter_config, env, tmp_path)
        # Paginated entity -> Paginated<T>; non-paginated -> List<T>.
        assert "Future<Paginated<Widget>> list(" in clients["widget_api.dart"]
        assert "Future<List<Note>> list(" in clients["note_api.dart"]
        # The paginated list carries page/page_size query params.
        assert "@Query('page') int? page" in clients["widget_api.dart"]
        assert "@Query('page_size') int? pageSize" in clients["widget_api.dart"]

    def test_filters_become_query_params(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _clients(model, flutter_config, env, tmp_path)["widget_api.dart"]
        # Whitelisted enum filter rendered with its concrete enum type.
        assert "@Query('status') WidgetStatus? status" in content
        # Non-whitelisted field is NOT a filter.
        assert "displayName" not in content.split("list({")[1].split("})")[0]

    def test_immutable_drops_update_endpoint(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _clients(model, flutter_config, env, tmp_path)["ledger_api.dart"]
        # Immutable: create + get + list present, but no PUT/Update.
        assert "@POST('/ledgers')" in content
        assert "@PUT(" not in content
        assert "UpdateLedgerRequest" not in content

    def test_api_disabled_emits_no_client(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        clients = _clients(model, flutter_config, env, tmp_path)
        assert "secret_api.dart" not in clients

    def test_output_path_derived_from_config(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_api_client(model, flutter_config, env, tmp_path)
        paths = {Path(o["path"]) for o in outputs}
        assert tmp_path / "lib" / "api" / "widget_api.dart" in paths


# --------------------------------------------------------------------------- #
# Request DTOs
# --------------------------------------------------------------------------- #


class TestRequestDtos:
    def test_create_and_update_present(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_request_dtos(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: str(o["content"]) for o in outputs}
        content = by_name["widget_requests.dart"]
        assert "abstract class CreateWidgetRequest with _$CreateWidgetRequest {" in content
        assert "abstract class UpdateWidgetRequest with _$UpdateWidgetRequest {" in content

    def test_immutable_skips_update_dto(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_request_dtos(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: str(o["content"]) for o in outputs}
        content = by_name["ledger_requests.dart"]
        assert "CreateLedgerRequest" in content
        assert "UpdateLedgerRequest" not in content

    def test_list_get_only_entity_has_no_dto_file(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_request_dtos(model, flutter_config, env, tmp_path)
        names = {Path(o["path"]).name for o in outputs}
        # Note exposes only list/get — no create/update, so no DTO file.
        assert "note_requests.dart" not in names
        # Secret (api disabled) likewise has no DTO file.
        assert "secret_requests.dart" not in names

    def test_dto_field_exclusion(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        create = {
            f["name"] for f in resolve_dto_fields(entity, flutter_config, "create")
        }
        update = {
            f["name"] for f in resolve_dto_fields(entity, flutter_config, "update")
        }
        # Auto-pk excluded everywhere.
        assert "id" not in create
        # Owner-scoped field injected by server -> not in the create payload.
        assert "ownerId" not in create
        # api_exclude_create / api_exclude_update honored.
        assert "internalNote" not in create
        assert "internalNote" not in update
        # Regular fields survive.
        assert "displayName" in create
        assert "unitPrice" in create

    def test_create_nullability_follows_required(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {
            f["name"]: f for f in resolve_dto_fields(entity, flutter_config, "create")
        }
        assert by_name["displayName"]["nullable"] is False  # required
        # Update DTO fields are always nullable (partial update).
        upd = {
            f["name"]: f for f in resolve_dto_fields(entity, flutter_config, "update")
        }
        assert upd["displayName"]["nullable"] is True

    def test_dto_renders_jsonkey_and_converter(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_request_dtos(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: str(o["content"]) for o in outputs}
        content = by_name["widget_requests.dart"]
        assert "fromJson: decimalFromJson, toJson: decimalToJson" in content
        assert "required Decimal unitPrice," in content


# --------------------------------------------------------------------------- #
# API barrel
# --------------------------------------------------------------------------- #


class TestApiIndex:
    def test_barrel_exports_enabled_clients_only(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_flutter_api_index(model, flutter_config, env, tmp_path)
        assert result is not None
        content = str(result["content"])
        assert "export 'widget_api.dart';" in content
        assert "export 'note_api.dart';" in content
        # api.enabled: false entity is not exported.
        assert "secret_api.dart" not in content

    def test_barrel_none_when_no_api(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        model = {"entities": {"X": {"fields": {}, "api": {"enabled": False}}}}
        assert generate_flutter_api_index(model, flutter_config, env, tmp_path) is None


# --------------------------------------------------------------------------- #
# Repositories (Phase-4 seam)
# --------------------------------------------------------------------------- #


class TestRepositories:
    def test_two_files_per_entity(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_repositories(model, flutter_config, env, tmp_path)
        names = {Path(o["path"]).name for o in outputs}
        assert "widget_repository.dart" in names
        assert "widget_repository_custom.dart" in names
        # Disabled entity gets no repository.
        assert "secret_repository.dart" not in names

    def test_custom_is_skip_if_exists_base_is_overwrite(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_repositories(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: o for o in outputs}
        assert by_name["widget_repository.dart"]["mode"] == "write"
        assert by_name["widget_repository_custom.dart"]["mode"] == "skip-if-exists"

    def test_base_delegates_to_client(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_repositories(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: str(o["content"]) for o in outputs}
        content = by_name["widget_repository.dart"]
        assert "final WidgetApi client;" in content
        assert "return client.list(" in content
        assert "class WidgetRepository {" in content

    def test_custom_extends_base(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_repositories(model, flutter_config, env, tmp_path)
        by_name = {Path(o["path"]).name: str(o["content"]) for o in outputs}
        content = by_name["widget_repository_custom.dart"]
        assert "class WidgetRepositoryCustom extends WidgetRepository {" in content


# --------------------------------------------------------------------------- #
# Pagination envelope (wire compatibility with the FastAPI stack)
# --------------------------------------------------------------------------- #


class TestPagination:
    def test_envelope_matches_backend(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        result = generate_flutter_pagination(flutter_config, env, tmp_path)
        content = str(result["content"])
        # Generic envelope + the snake_case wire keys the FastAPI stack emits.
        assert "abstract class Paginated<T> with _$Paginated<T> {" in content
        assert "required List<T> items," in content
        assert "@JsonKey(name: 'page_info') required PageInfo pageInfo," in content
        assert "@JsonKey(name: 'page_size') required int pageSize," in content
        assert "@JsonKey(name: 'total_items') required int totalItems," in content
        assert "@JsonKey(name: 'has_next') required bool hasNext," in content
        assert "genericArgumentFactories: true" in content

    def test_path_uses_api_core(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        result = generate_flutter_pagination(flutter_config, env, tmp_path)
        assert result["path"] == tmp_path / "lib" / "core" / "pagination.dart"


# --------------------------------------------------------------------------- #
# Dio setup (two-file)
# --------------------------------------------------------------------------- #


class TestDioSetup:
    def test_two_files_base_and_custom(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        outputs = generate_dio_setup(flutter_config, env, tmp_path, {})
        by_name = {Path(o["path"]).name: o for o in outputs}
        assert by_name["api_client.dart"]["mode"] == "write"
        assert by_name["api_client_custom.dart"]["mode"] == "skip-if-exists"

    def test_base_wires_baseurl_and_hook(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        outputs = generate_dio_setup(flutter_config, env, tmp_path, {})
        base = next(
            str(o["content"])
            for o in outputs
            if Path(o["path"]).name == "api_client.dart"
        )
        assert "Dio buildApiClient({" in base
        assert "configureApiClient(dio);" in base
        # No auth -> no interceptor import.
        assert "auth_interceptor" not in base

    def test_base_adds_interceptor_when_auth_enabled(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        outputs = generate_dio_setup(
            flutter_config, env, tmp_path, {"auth": {"strategy": "api-key"}}
        )
        base = next(
            str(o["content"])
            for o in outputs
            if Path(o["path"]).name == "api_client.dart"
        )
        assert "AuthInterceptor(" in base
        assert "/core/auth_interceptor.dart" in base


# --------------------------------------------------------------------------- #
# Auth interceptor (conditional on auth.strategy)
# --------------------------------------------------------------------------- #


class TestAuthInterceptor:
    def test_none_without_strategy(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        assert generate_auth_interceptor(flutter_config, env, tmp_path, {}) is None

    def test_api_key_uses_configured_header(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        project = {"auth": {"strategy": "api-key", "header_name": "X-Shop-Key"}}
        result = generate_auth_interceptor(flutter_config, env, tmp_path, project)
        assert result is not None
        content = str(result["content"])
        assert "class AuthInterceptor extends Interceptor {" in content
        assert "static const String headerName = 'X-Shop-Key';" in content

    def test_api_key_defaults_header(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        project = {"auth": {"strategy": "api-key"}}
        result = generate_auth_interceptor(flutter_config, env, tmp_path, project)
        assert result is not None
        assert "headerName = 'X-API-Key';" in str(result["content"])

    def test_bcrypt_session_cookie_passthrough(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        project = {"auth": {"strategy": "bcrypt-session"}}
        result = generate_auth_interceptor(flutter_config, env, tmp_path, project)
        assert result is not None
        content = str(result["content"])
        # Session strategy -> CSRF double-submit, no API-key header.
        assert "csrfCookieName = 'csrf_token';" in content
        assert "csrfHeaderName = 'X-CSRF-Token';" in content
        assert "headerName" not in content


# --------------------------------------------------------------------------- #
# Project-agnostic guarantees (the cardinal rule) — Phase-2 templates
# --------------------------------------------------------------------------- #

_API_TEMPLATE_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "model_generator"
    / "stacks"
    / "flutter"
    / "templates"
)


class TestProjectAgnosticPhase2:
    def test_no_hardcoded_entity_names(self) -> None:
        banned = ["Widget", "Ledger", "Portfolio", "ApiKey", "Transaction", "Note"]
        for name in (
            "api/retrofit_client.dart.j2",
            "api/request.dart.j2",
            "api/repository.dart.j2",
            "api/index.dart.j2",
        ):
            text = (_API_TEMPLATE_DIR / name).read_text(encoding="utf-8")
            for entity in banned:
                assert entity not in text, f"{entity} hardcoded in {name}"

    def test_no_hardcoded_paths_or_packages(self) -> None:
        banned = [
            "backend/src",
            "lib/app_api",
            "lib/probe_api",
            "package:app_api",
            "package:shop_client",
        ]
        for template in _API_TEMPLATE_DIR.rglob("*.j2"):
            text = template.read_text(encoding="utf-8")
            for frag in banned:
                assert frag not in text, f"{frag} hardcoded in {template.name}"

    def test_client_imports_track_package_name(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        cfg = dict(flutter_config)
        cfg["flutter"] = {"package_name": "custom_pkg"}
        content = _clients(model, cfg, env, tmp_path)["widget_api.dart"]
        assert "package:custom_pkg/models/widget.dart" in content
        assert "package:custom_pkg/core/pagination.dart" in content
        # No default package name leaks when overridden.
        assert "package:app_api/" not in content
