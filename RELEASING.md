# Releasing llm-parliament

This document describes how to publish a new version of `llm-parliament` to PyPI.

## One-time setup

1. **Create a PyPI account** at <https://pypi.org/account/register/>.

2. **Create an API token** at <https://pypi.org/manage/account/token/>.
   - Scope: "Entire account" for the first publish.
   - Narrow to project scope (`Project: llm-parliament`) after the first successful publish.
   - Save the token — you only see it once.

3. **Configure twine** by creating `~/.pypirc`:

   ```ini
   [pypi]
   username = __token__
   password = pypi-<your-pypi-token-here>            # the full token, including the `pypi-` prefix

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-<your-testpypi-token-here>        # separate TestPyPI token
   ```

   Then `chmod 0600 ~/.pypirc`.

4. **Verify the package name is available** on PyPI by visiting
   <https://pypi.org/project/llm-parliament/> — it should 404 before the
   first publish.

5. **Install build tools globally** (one-time):

   ```bash
   pipx install build
   pipx install twine
   ```

## First publish (v0.1.0)

For the very first publish, do a TestPyPI rehearsal so any metadata or
classifier issues surface before they hit real PyPI (where you cannot
overwrite versions).

```bash
# Standing on main, all changes merged, all tests green.

# Build wheel + sdist
python -m build

# Validate metadata
twine check dist/*

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Smoke-test the install from TestPyPI
pipx install \
  --pip-args "--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/" \
  llm-parliament
parliament doctor
pipx uninstall llm-parliament

# Happy? Real upload:
twine upload dist/*

# Tag the release
git tag v0.1.0
git push origin v0.1.0

# Verify
pipx install llm-parliament
parliament doctor
```

## Subsequent releases

Skip TestPyPI rehearsal for non-major releases.

```bash
# Bump version in pyproject.toml (semver: major.minor.patch).
# Commit the bump:
git add pyproject.toml
git commit -m "chore: bump version to X.Y.Z"

# Build, check, upload
python -m build
twine check dist/*
twine upload dist/*

# Tag and push
git tag vX.Y.Z
git push origin main vX.Y.Z

# Smoke
pipx install --upgrade llm-parliament
parliament doctor
```

## What can break and how to recover

- **Name conflict on first publish:** PyPI returns `400 File already exists`
  if `llm-parliament` is taken. Pick a different name in `pyproject.toml` and
  redo from the build step.
- **Metadata error:** `twine check` will catch most. Read the error, fix
  classifiers / license / readme rendering, re-run `python -m build`.
- **Bug in published version:** PyPI does not allow overwriting an
  existing version. You can only **yank** a version (hides it from new
  installs but doesn't delete it) and publish a patch. Yank via the PyPI
  web UI under "Manage project → Releases".
- **Wrong file in `dist/`:** delete the `dist/` directory and rebuild.

## Notes

- We do **not** use GitHub Actions for publishing right now. Manual local
  release is sufficient for a solo project. Revisit if release frequency
  grows or if multiple maintainers join.
- The `dist/` directory is gitignored — never commit build artifacts.
- `~/.pypirc` contains live tokens. Keep it `chmod 0600` and never commit
  it to any repo.
