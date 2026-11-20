# Contributing to skill-exposure-manifest

Bug reports and patches are welcome. You do not need to ask before opening a pull request for a bug fix.

## Before you start

- **A wrong resolution:** open an issue with the policy entry, the query, the manifest entry you expected, and the entry you got. A small skills tree that reproduces it is the most useful evidence.
- **A change to what counts as a valid name:** open an issue first. Loosening exact matching changes every caller.
- **A security problem:** do not open a public issue. See [SECURITY.md](SECURITY.md).

## Set up

```sh
git clone https://github.com/elfenomenokim/skill-exposure-manifest
cd skill-exposure-manifest
python3 -m pip install . pytest
python3 -m pytest -q tests
python3 -m compileall -q src
SKILLS_DIR=/path/to/skills python3 docs/bench/derive.py --write
```

The suite builds its own fixture `SKILL.md` tree and policy in a temporary directory, so it needs no
skills checkout. Never point a test at a live skills directory. `docs/bench/derive.py` prints the
measurement and replaces `docs/bench/derive.json` only with `--write`.

## Rules a patch must keep

- Resolution compares exact strings. No case folding, trimming, or substring search.
- A stale digest, a duplicate name, a symlink, or a path above the root fails; it never falls back.
- Derivation and resolution stay read-only. Do not add a write path to this package.
- Layout stays a caller input. A new path convention belongs in `families=`, `generated_root=`, or a
  registration's `source_path`, not in a constant.
- Keep the error type `ExposureManifestError` for every refusal, so callers catch one thing.

## What a good patch has

- **A fixture tree** that fails before the change and passes after it.
- **A line under Unreleased** in [CHANGELOG.md](CHANGELOG.md) when a caller will notice.
- **The platforms you did not test** written in the pull request. `.github/workflows/tests.yml` runs the
  suite on Ubuntu, macOS and Windows with Python 3.9 and 3.13.

## Licence

Contributions are licensed under the MIT licence in [LICENSE](LICENSE).
