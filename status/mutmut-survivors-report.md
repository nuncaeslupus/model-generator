# Mutmut Survivors Report — 2026-06-24

Full run complete: **9,915 mutants, 6,518 killed / 3,397 survived (66% kill rate).**
Generated locally with `mutmut 3.4.0` (3.5.0 is broken — see CLAUDE.md; the pin
`<3.5.0` is now enforced in `pyproject.toml`).

Regenerate this report any time with:

```bash
uv run python .claude/skills/mutmut-report/analyze_mutmut.py --max 50
```

## Per-batch

| Batch                  | Total | Killed | Survived | Kill % |
|------------------------|------:|-------:|---------:|-------:|
| batch-1-utils          | 1610  | 1183   | 427      | 73%    |
| batch-2-generators     | 1872  | 1343   | 529      | 72%    |
| batch-3-conftest       | 1233  | 473    | 760      | 38%    |
| batch-4-flutter-api    | 1546  | 965    | 581      | 62%    |
| batch-5-flutter-gen    | 464   | 344    | 120      | 74%    |
| batch-6-generate       | 1631  | 1149   | 482      | 70%    |
| batch-7-infrastructure | 1559  | 1061   | 498      | 68%    |

Core logic is well-tested: `validate` 97%, `constraints` 94%, `parser` 91%,
`enums` 87%. Low kill-rate modules are interactive wizard glue and string-template
emission — mutation testing has poor signal there.

## Triage of the 113 classifier-flagged "real gaps"

The classifier overcounts. Reading the diffs, most flagged gaps are noise:

### Noise — accept, do NOT chase
- **`encoding="utf-8"` → `None` / `"UTF-8"`** (~12 survivors: `parser`, `enums`,
  `constraints`, `validate.load_schema#14/16`). **Equivalent**: `"UTF-8"` is the
  same codec (case-insensitive lookup); `encoding=None` resolves to the locale
  default (UTF-8 here). The classifier misses this class — consider teaching it
  upstream (see below).
- **`XX`-wrapped string literals & case-swaps** in `print()` / menu prompts /
  error messages / emitted-template text (`run_menu`'s 19, most of `generate`'s
  482, most of the skipped modules). Killing these = asserting exact UI/output
  strings. Brittle, low value.
- **Template-render kwargs** (`mode="append"`, `config=config`,
  `section_header="ENUMS"` → `None`/missing). Tests check the *output file*, not
  the call arguments.

### Worth a test (~20–30 survivors, tightly clustered)

1. **`.get("entities", {})` → `None`/missing in `database.py`** — the one clean,
   high-yield win. ~14 survivors across:
   - `generate_database_model#14/16/38/40`
   - `generate_init#17/19/61/63`
   - `generate_factories#22/24/33/35/73/75`

   A single characterization test **per function** kills the whole cluster: call
   the function with a model dict that has **no `entities` key**. The real `{}`
   default yields empty/valid output (per-entity → `[]`; `generate_init` → `None`);
   the `None` mutant crashes on `.keys()` / `.items()` / `for ... in None`.
   Same shape applies to `.get("domain", "unknown")` and `.get("table", …)`
   defaults in the same file.

   Setup notes (from `tests/test_generators.py`): use the `project_env` fixture
   (`project_root, config, env`). For `generate_factories`, pass `constraints={}`
   to avoid the filesystem `load_shared_constraints` call.

2. **Boolean `and`→`or` swaps** — real logic gaps; test the false branch:
   - `flutter/paths.py::package_name#9` —
     `isinstance(name, str) and name.strip()` → `or`. Test with a non-str value
     and with an empty/whitespace string.
   - `generate.py::_cleanup_selective#39` —
     `isinstance(path, str) and (path.endswith(".py") or ...)` → `or`. Test with
     a str path that has the wrong extension.

3. **`migrations.py::generate_migration_init` `mkdir(parents=True, …)`**
   (#27/29/31) — narrow but legitimate: build the versions dir under a
   non-existent parent so `parents=True` actually matters.

### Auto-classified, accept as-is
- **Equivalent (3)** — `cast()` no-ops, `.get(k, False)` → `None` (both falsy).
- **Untestable (12)** — `sys.exit()` code values, `print()` in error paths.

## Skipped modules (>50 survivors, not detail-analyzed)

`test_runner` (56), `clean` (70), `quality` (70), `prompts` (77), `output` (89),
`loaders` (94), `project_setup` (95), `flutter.generators` (120), `api` (138),
`actions.generate` (139), `flutter.api` (262), `flutter.fields` (319),
`generate` (482), `infrastructure` (498), `conftest_generator` (760).

Sampling confirmed these are dominated by the **same low-value classes** at scale
(`XX`-wrapped strings, dict-key case-swaps, `.get` default mutations). Not a
hidden trove of real bugs. To inspect one: `--module <name> --max 9999`.

## Follow-up ideas (not yet done)

- **Teach the classifier `encoding=` is EQUIVALENT.** `analyze_mutmut.py` lives in
  the `my-skills` subtree (`.claude/skills/mutmut-report/`); the fix belongs
  upstream at `github.com/nuncaeslupus/my-skills`, not edited in-repo (it'd be
  overwritten by `make update-skills`).
- **Latent bug in `scripts/mutmut_batch.py`:** `ensure_workspace` runs
  `subprocess.run(["uv","run","mutmut","run"], timeout=35)`. On timeout Python
  kills the `uv` child, but `mutmut` is a grandchild and gets **orphaned**, so it
  keeps running to completion in the background. (That's how this full run
  happened by accident.) If made deterministic it should `start_new_session=True`
  + kill the process group, or invoke `mutmut` directly without the `uv` wrapper.
