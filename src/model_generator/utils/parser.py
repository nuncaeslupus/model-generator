import ast
import re
from pathlib import Path
from typing import Any


def scan_model_files(models_dir: Path) -> list[dict[str, Any]]:
    """
    Scan model files and extract entity class names using AST.

    Robustly parses Python files to find classes inheriting from Base,
    ignoring formatting differences that might break regex.
    """
    domains = []
    skip_files = {"__init__.py", "base.py", "constraints.py", "enums.py"}

    if not models_dir.exists():
        return []

    for model_file in sorted(models_dir.glob("*.py")):
        if model_file.name in skip_files:
            continue

        try:
            content = model_file.read_text()
            tree = ast.parse(content)

            entities = []

            # Find classes inheriting from Base
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    is_model = False
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == "Base":
                            is_model = True
                            break

                    if is_model:
                        entities.append(node.name)

            if entities:
                # Extract section header from comments
                # (still regex as AST doesn't preserve comments easily)
                section_match = re.search(
                    r"#\s*={10,}\s*\n#\s*([A-Z][A-Z0-9 &_]+)\s*\n", content
                )
                section = section_match.group(1) if section_match else None

                domains.append(
                    {
                        "name": model_file.stem,
                        "file": model_file.stem,
                        "section": section,
                        "entities": entities,
                    }
                )
        except SyntaxError:
            # Skip files with syntax errors
            print(f"  Warning: Could not parse {model_file} (syntax error)")
            continue
        except Exception as e:
            print(f"  Warning: Error parsing {model_file}: {e}")
            continue

    return domains


def scan_api_model_files(api_models_dir: Path) -> list[dict[str, Any]]:
    """
    Scan API model files and extract model class names using AST.

    Finds classes ending in 'Response' or 'Request'.
    """
    domains = []
    skip_files = {"__init__.py"}

    if not api_models_dir.exists():
        return []

    # Find all unique domain prefixes from files
    domain_names = set()
    for model_file in api_models_dir.glob("*.py"):
        if model_file.name in skip_files:
            continue
        # Extract domain from filename (e.g., "users" from "users_response.py")
        if model_file.stem.endswith("_response"):
            domain_names.add(model_file.stem.replace("_response", ""))
        elif model_file.stem.endswith("_requests"):
            domain_names.add(model_file.stem.replace("_requests", ""))

    for domain_name in sorted(domain_names):
        domain_info: dict[str, Any] = {
            "name": domain_name,
            "section": domain_name.upper().replace("_", " ") + " MODELS",
            "response_models": [],
            "request_models": [],
        }

        # Scan response file
        response_file = api_models_dir / f"{domain_name}_response.py"
        if response_file.exists():
            try:
                content = response_file.read_text()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name.endswith(
                        "Response"
                    ):
                        domain_info["response_models"].append(node.name)
            except Exception as e:
                print(f"  Warning: Error parsing {response_file}: {e}")

        # Scan request file
        request_file = api_models_dir / f"{domain_name}_requests.py"
        if request_file.exists():
            try:
                content = request_file.read_text()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name.endswith("Request"):
                        domain_info["request_models"].append(node.name)
            except Exception as e:
                print(f"  Warning: Error parsing {request_file}: {e}")

        if domain_info["response_models"] or domain_info["request_models"]:
            domains.append(domain_info)

    return domains
