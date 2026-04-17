# LEAM Release Checklist

Use this checklist before publishing a new LEAM release to GitHub and PyPI.

## Versioning

- Update `project.version` in `pyproject.toml`.
- Update the release notes source you plan to publish from.
- Make sure the intended Git tag matches the package version exactly:
  `v<version>`.

## Validation

- Run the test suite:

```powershell
py -3.11 -m pytest -q
```

- Run Ruff exactly as CI does:

```powershell
py -3.11 -m ruff check src tests
```

- Run mypy exactly as CI does:

```powershell
py -3.11 -m mypy src
```

- Build source and wheel distributions:

```powershell
py -3.11 -m build
```

- Verify package metadata and README rendering:

```powershell
py -3.11 scripts\twine_check.py
```

- Run the Windows distribution smoke test. This installs the built wheel into a
  fresh virtual environment and verifies the packaged launchers:

```powershell
py -3.11 scripts\dist_smoke_test.py
```

- On a fresh Windows Python 3.11 install with at least one supported simulator
  runtime available, verify both desktop launch paths before publishing:

```powershell
py -3.11 -m pip install --force-reinstall dist\leam-<version>-py3-none-any.whl
leam-desktop
py -3.11 -m leam.desktop
```

- Confirm the launchpad opens normally when a supported CST or HFSS runtime is
  available.
- Confirm the launchpad stays blocked with a clear runtime message when neither
  backend is available.
- Confirm `leam-configure --print-example` still works for advanced setup.

## Documentation

- Review `docs/getting_started.md` and `docs/workflow_reference.md` when the
  release changes desktop behavior.
- Review `docs/python_api.md` when API or programmatic example access changes.
- Review `README.md`.
- Review `site/index.html`.
- Make sure links in `pyproject.toml` still point to the right pages.

## GitHub Release

- Merge the final release commit to the release branch.
- Create and push the version tag in the form `v<version>`.
- Publish the GitHub release from that tag.
- Confirm the workflow attaches the built `.whl` and `.tar.gz` files to the
  GitHub release.

## PyPI Release

- Confirm the GitHub release workflow completed successfully.
- Confirm the package appears on PyPI with the expected version.
- Confirm the PyPI project page renders the README and documentation links
  correctly.

## Post-Release Checks

- Confirm the published package resolves from PyPI on Windows:
  `py -3.11 -m pip install --upgrade leam`.
- Confirm the release notes summarize user-visible changes accurately.
