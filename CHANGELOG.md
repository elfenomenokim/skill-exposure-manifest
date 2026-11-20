# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-20

### Added

- `exclusions` in the policy file: a skill a project deliberately keeps outside the exposure
  policy. Each entry names a real `SKILL.md`, its frontmatter name and a reason, and an exclusion
  may not also be registered. `policy_exclusions(project_root, policy_path)` returns the validated
  list.
- `unlisted_skills(project_root, policy_path)` returns every skill directory that is neither
  registered nor excluded, so a new skill cannot be silently absent from the policy.
- `enumerate_skill_dirs(project_root, generated_root=...)` lists the runtime skill directories the
  two functions above measure against.
- The policy schema accepts `cch-skill-exposure-policy/2` (registrations plus exclusions) and still
  reads `/1`.
- `tests/` runs from the package alone: a fixture `SKILL.md` tree and a policy in a temporary
  directory cover derive/resolve exactness, aliases, case and partial refusal, a stale digest, a
  symlink, a path escape, exclusion validation and `unlisted_skills`.
- `.github/workflows/tests.yml` runs that suite on Ubuntu, macOS and Windows; `claude.yml` and
  `opencode-review.yml` give the repository its review checks.

### Changed

- `docs/bench/derive.py` prints the measurement and writes `docs/bench/derive.json` only with
  `--write`, so following the contributing steps no longer dirties the tree.
- `SKILLS_DIR` defaults to the repository root instead of a parent checkout, which an exported
  repository does not have.

## [0.1.0] - 2026-11-19

### Added

- `derive_manifest(root, registrations=None)` builds a deterministic manifest from every regular
  `SKILL.md` under a root, binding each canonical name, its exact aliases, the relative source path, the
  source SHA-256, and the runtime policy.
- `resolve_skill(query, manifest, *, source_root)` accepts one exact canonical name or alias and re-reads
  the bound source before returning it.
- `canonical_policy_manifest(project_root, policy_path)` derives the manifest straight from canonical
  project sources, without needing a runtime home or a projection directory.
- `resolve_canonical_skill(query, *, project_root, policy_path)` resolves a name or alias to its canonical
  file and reports whether the policy hides it.
- Layout is a caller input: a registration's own `source_path` wins, `families=` covers generated
  persona prefixes, and `generated_root=` names their directory. No layout is a constant in the package.

[Unreleased]: https://github.com/elfenomenokim/skill-exposure-manifest/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/elfenomenokim/skill-exposure-manifest/releases/tag/v0.2.0
[0.1.0]: https://github.com/elfenomenokim/skill-exposure-manifest/releases/tag/v0.1.0
