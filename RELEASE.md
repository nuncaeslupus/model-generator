# Releasing

Releases are automated via the **`v*` tag → PyPI + GitHub release** pipeline in
[`.github/workflows/release.yml`](./.github/workflows/release.yml). The single
source of truth for the version is `pyproject.toml`'s `[project].version`;
everything else is derived from it.

## One-time PyPI setup (trusted publishing)

The release workflow uploads to PyPI using **trusted publishing (OIDC)** — no
API token is stored anywhere. PyPI mints the upload credential after verifying
the upload came from this repo's `release.yml` workflow in the `pypi`
environment. This must be registered **once** before the first release, in a
browser (it cannot be scripted):

1. Log into <https://pypi.org>.
2. Go to your account → **Publishing** → **Add a new pending publisher**
   (the project does not exist on PyPI yet, so it must be a *pending*
   publisher — it gets created on first upload).
3. Fill in exactly (note: the PyPI **project name** is `model-generator-kit` — the
   name `model-generator` was unavailable — but the GitHub **repository** is
   still `model-generator`; these are independent):
   - PyPI project name: `model-generator-kit`
   - Owner: `nuncaeslupus`
   - Repository: `model-generator`
   - Workflow filename: `release.yml`
   - Environment: `pypi`
4. Save.

> The `pypi` GitHub environment also lets you require a manual approval before
> the upload step, if you want a human gate on releases. Configure it under
> the repo's **Settings → Environments → pypi**.

## Cutting a release

From a clean `main`:

```bash
# 1. Bump the version and propagate it everywhere it appears
vim pyproject.toml            # edit [project].version
make version-sync             # -> src/model_generator/__init__.py + README footer
make check-version-sync       # sanity check

# 2. Update CHANGELOG.md
#    - rename the [Unreleased] section to [X.Y.Z] — YYYY-MM-DD
#    - add a fresh empty [Unreleased] section on top

# 3. Commit the bump + changelog (on a branch -> PR -> merge to main)
git add -u && git commit -m "chore(release): bump to X.Y.Z"
git push

# 4. Once the bump has merged, tag main HEAD and push the tag.
#    Run this from an up-to-date main:
git checkout main && git pull
make tag-release
```

> **Always use `make tag-release` for step 4.** It tags the *current main
> HEAD* with `v<pyproject-version>` and refuses to run unless you are on a
> clean `main` that is in sync with `origin/main`, version strings are
> consistent, and the tag does not already exist. This makes the most common
> release mistake — **tagging the wrong commit** (e.g. an older release commit
> whose `pyproject.toml` still says the previous version) — impossible. If you
> tag by hand and point at the wrong commit, the `build` job fails on the
> tag↔version check and nothing is published; see *Failure recovery* below.

Pushing the tag triggers `release.yml`:

1. **build** — verifies the tag matches `pyproject.toml.project.version`, runs
   `make check-version-sync`, builds wheel + sdist, runs `twine check`.
2. **publish-pypi** — uploads `dist/*` to PyPI via trusted publishing (no
   token). Gated behind the `pypi` environment.
3. **github-release** — creates the GitHub release from the tag, using
   `CHANGELOG.md` as the body, and attaches the built distributions.

You do not need to run anything locally after `git push origin vX.Y.Z`.

## Do not also `make publish` locally

The workflow is the canonical publish path. `make publish` is a fallback for
when the workflow is unavailable. To prevent the two from racing, `make
publish` refuses when a `v<current-pyproject-version>` tag already exists on
`origin` (a second upload of the same files fails with a PyPI 400 "File already
exists"). Use `make publish-force` only when the workflow is genuinely broken.

## Failure recovery

- **Tag ↔ version mismatch / tag on the wrong commit**: the `build` job fails
  early on the "Verify tag matches pyproject.toml version" step, so nothing is
  published. Move the tag onto the correct commit:
  ```bash
  git push origin :refs/tags/vX.Y.Z   # delete the bad remote tag
  git tag -d vX.Y.Z                    # delete locally
  git checkout main && git pull        # the commit whose pyproject == X.Y.Z
  make tag-release                     # re-tag main HEAD and push
  ```
  (`make tag-release` would have prevented this — prefer it over a manual
  `git tag`.)
- **PyPI upload fails after build succeeded**: `dist/` artifacts are retained
  for 7 days on the build job. Re-run the `publish-pypi` job from the Actions
  UI.
- **PyPI version already exists**: PyPI refuses to overwrite a published
  version. Bump to the next patch and repeat the release flow.

## What counts as each kind of bump (semver)

- **PATCH** (X.Y.**Z**) — bug fixes to the generator or templates, refactors,
  doc-only changes. Output of a regeneration is unchanged or strictly fixed.
- **MINOR** (X.**Y**.0) — backwards-compatible additions: new field types,
  new generation targets, new optional spec keys, a new stack.
- **MAJOR** (**X**.0.0) — breaking changes to the JSON spec schema or to the
  shape of generated code that would require existing specs to change.
