# Releasing

HERMESS is distributed on PyPI as `hermess`. A PyPI release is an immutable
snapshot; a version number, once published, can never be reused (only yanked).
Users get new features when a new version is published and they upgrade, so
the repository can evolve continuously between releases.

Versions follow Semantic Versioning, `MAJOR.MINOR.PATCH`.

## Choosing the next version

Compare main against the last release tag and pick the highest bump that any
single change requires.

- **PATCH** (`x.y.Z+1`): bug fixes, documentation, performance work, internal
  refactors. Existing user scripts and system parameter files run unchanged
  and, apart from the fixed bug, produce the same results.
- **MINOR** (`x.Y+1.0`): backward-compatible additions. New device models,
  strategies, shipped systems, disturbances, API functions, or options whose
  defaults preserve old behavior. Deprecations belong here too, as long as the
  old name keeps working and emits a `DeprecationWarning`.
- **MAJOR** (`X+1.0.0`): anything that breaks existing users. Renamed or
  removed public API or device/parameter names, removal of deprecated aliases,
  changed defaults that alter simulation results, or regenerated reference
  behavior that shifts results beyond documented tolerances (unless the old
  results were a bug, which is a PATCH and must be called out in the
  changelog).

Rule of thumb: if a user's existing script and system folder run unchanged
with the same results, the release is not MAJOR. For a risky change, publish a
release candidate first (`X.0.0rc1`); pip only installs it with `--pre`.

## Release checklist

1. Main is green (`uv run pytest -q`) and the working tree is clean.
2. Pick the version with the rules above, then update every version string:
   - `pyproject.toml`, `[project] version` (drives the package and the docs)
   - `CITATION.cff`, `version:` and `date-released:`
   - the fallback strings in `hermess/__init__.py` and `hermess/__main__.py`
3. Add a dated `CHANGELOG.md` section, grouped Added / Changed / Fixed, with
   breaking changes marked in bold.
4. `uv lock && uv sync --locked && uv run pytest -q`.
5. Commit as `Release X.Y.Z` and push to main.
6. Tag and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
7. Publish a GitHub release for the tag, titled `HERMESS X.Y.Z`, body taken
   from the changelog section. Publishing the release triggers
   `.github/workflows/publish.yml`, which builds with uv and uploads to PyPI
   via trusted publishing (GitHub environment `pypi`).
8. Verify: the publish workflow is green, the version appears on
   https://pypi.org/project/hermess/, and `pip install hermess==X.Y.Z` works
   in a scratch venv.
9. For MAJOR and MINOR releases, consider depositing the release as a new
   version of ETH Research Collection item 691195 and updating the citation
   in `README.md` and `docs/source/index.rst` (they cite a specific deposited
   version and are not bumped otherwise).
