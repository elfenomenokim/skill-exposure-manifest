# AGENTS.md

## Layout

- `src/skill_exposure_manifest/core.py`: the whole library — path validation, discovery, hashing, manifest
  derivation, and resolution. Keep it in one module; the value is a small auditable surface.
- `src/skill_exposure_manifest/__init__.py`: the public names and the version.
- `docs/bench/derive.py`: re-measures derive and resolve and prints `docs/bench/derive.json`; only
  `--write` replaces the committed file.
- `tests/`: the package-local contract suite, run against a temporary fixture tree.
- `.github/workflows/`: `tests.yml` on Ubuntu, macOS and Windows, plus the review workflows.
- `docs/logo.svg`: the mark used in the README.
- `public.json`: export allowlist and repository metadata.

## Commands

Run from the repository root:

```sh
python3 -m compileall -q src
python3 -m pytest -q tests
python3 -c "import sys; sys.path.insert(0,'src'); import skill_exposure_manifest as m; print(m.__version__)"
SKILLS_DIR=/path/to/skills python3 docs/bench/derive.py --write
```

`tests/test_manifest.py` builds its own `SKILL.md` tree and policy in a temporary directory, so it
needs no skills checkout and no install. `tests/conftest.py` puts `src/` on the path when the
package is not installed; CI installs the package first and tests the installed copy.

## Changes

- Resolution is exact string equality against canonical names and aliases. Do not add case folding,
  trimming, substring matching, or fuzzy fallbacks.
- Every refusal raises `ExposureManifestError`. Do not introduce a second exception type.
- Derivation and resolution stay read-only and free of import-time side effects.
- Refuse symlinks and any path that escapes the root, lexically before resolution.
- Paths are POSIX relative paths. Refuse backslashes on every platform so a manifest keeps one meaning.
- Layout belongs to the caller: `source_path` on the registration, `families=` and `generated_root=`
  arguments. Never add a project-specific path constant.
- Keep README.md, README.ko.md, the `pyproject.toml` description and `public.json` aligned.
- A local commit is not publication. Version bumps and PyPI uploads require the maintainer's release
  instruction.

## Hard don'ts

- Do not read the whole filesystem to find skills. Discovery is scoped to the root the caller passed.
- Do not cache across resolves. A stale-but-fast answer defeats the purpose of the digest check.
- Do not write to the skills tree from any function in this package, including "repair" helpers.
