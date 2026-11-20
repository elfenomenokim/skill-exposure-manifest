#!/usr/bin/env python3
"""Build and resolve a small, content-bound skill exposure manifest.

The manifest is derived from the ``SKILL.md`` files below a caller-supplied
root.  A registration can add exact aliases and a runtime policy, while an
unregistered source receives the conservative visible tier-one default.  The
resolver accepts only an exact canonical name or alias and checks the bound
source bytes again before returning it.

This module is intentionally filesystem-only and has no writer or import-time
side effect.  A malformed registration, source, manifest, or binding raises
``ExposureManifestError`` rather than guessing a name or path.

Layout is a caller input, never a convention baked into this file: a canonical
source is the registration's own ``source_path`` when that file exists, and only
then a family mapping (``families=``) or the flat ``<name>/SKILL.md`` fallback.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_SCHEMA = "cch-skill-exposure-manifest/1"
DEFAULT_RUNTIME_POLICY = {"tier": 1, "model_visible": True}
_HEX_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_REGISTRATION_KEYS = frozenset(
    {"canonical_name", "aliases", "source_path", "runtime_policy"}
)
_RUNTIME_POLICY_KEYS = frozenset({"tier", "model_visible"})
_EXCLUSION_KEYS = frozenset({"canonical_name", "source_path", "reason"})
# /1 had registrations only; /2 adds the explicit ``exclusions`` list.
POLICY_SCHEMAS = frozenset(
    {"cch-skill-exposure-policy/1", "cch-skill-exposure-policy/2"}
)


class ExposureManifestError(ValueError):
    """Raised when exposure-manifest authority is malformed or stale."""


def _fail(message: str) -> None:
    raise ExposureManifestError(message)


def _root_path(value: Path | str, *, label: str) -> Path:
    if not isinstance(value, (Path, str)):
        _fail(f"{label} must be a path")
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as exc:
        _fail(f"{label} is not an accessible directory: {exc}")
    if not root.is_dir():
        _fail(f"{label} is not a directory: {root}")
    return root


def _validate_name(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        _fail(f"{label} must not have surrounding whitespace or NUL bytes")
    if "\n" in value or "\r" in value:
        _fail(f"{label} must be a single line")
    return value


def _normal_relative_path(value: Any, *, label: str) -> str:
    """Return a normalized POSIX relative path, refusing escape syntax.

    Backslashes are refused even on POSIX so a manifest made on one host
    cannot acquire a different meaning on another host.  ``..`` is refused
    lexically before resolution; this keeps path authority easy to audit.
    """

    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty relative path")
    if "\x00" in value or "\\" in value:
        _fail(f"{label} contains an invalid path character")
    try:
        candidate = PurePosixPath(value)
    except (TypeError, ValueError) as exc:
        _fail(f"{label} is not a valid path: {exc}")
    if candidate.is_absolute() or value.startswith("/"):
        _fail(f"{label} must stay below the source root")
    if ".." in candidate.parts:
        _fail(f"{label} escapes the source root")
    normalized = candidate.as_posix()
    if not normalized or normalized == ".":
        _fail(f"{label} must identify a file")
    return normalized


def _below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_source(root: Path, relative_path: str, *, label: str) -> Path:
    """Resolve a source path while refusing symlink and root escapes."""

    parts = PurePosixPath(relative_path).parts
    path = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor = cursor / part
        try:
            if cursor.is_symlink():
                _fail(f"{label} follows a symlink: {relative_path}")
        except OSError as exc:
            _fail(f"{label} cannot inspect path {relative_path}: {exc}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _fail(f"{label} is missing or unreadable: {relative_path}: {exc}")
    if not _below(resolved, root):
        _fail(f"{label} escapes the source root: {relative_path}")
    if not path.is_file() or resolved.name != "SKILL.md":
        _fail(f"{label} must be a regular SKILL.md file: {relative_path}")
    return path


def _read_source(path: Path, *, label: str) -> tuple[bytes, str]:
    try:
        data = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        _fail(f"{label} is unreadable: {path}: {exc}")
    return data, hashlib.sha256(data).hexdigest()


def _frontmatter_name(data: bytes, *, label: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail(f"{label} is not UTF-8: {exc}")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        _fail(f"{label} is missing YAML frontmatter")

    found: str | None = None
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        match = re.match(r"^\s*name\s*:\s*(.*?)\s*$", line)
        if match is None:
            continue
        if found is not None:
            _fail(f"{label} declares name more than once")
        value = match.group(1)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found = _validate_name(value, label=f"{label} frontmatter name")
    if not closed:
        _fail(f"{label} has an unterminated YAML frontmatter block")
    if found is None:
        _fail(f"{label} frontmatter needs a name")
    return found


def _discover(root: Path) -> dict[str, dict[str, Any]]:
    """Discover and fingerprint every regular ``SKILL.md`` below ``root``."""

    try:
        candidates = sorted(
            root.rglob("SKILL.md"), key=lambda item: item.as_posix()
        )
    except (OSError, RuntimeError) as exc:
        _fail(f"skill source discovery failed: {exc}")

    discovered: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            _fail(f"discovered source is outside root: {candidate}: {exc}")
        normalized = _normal_relative_path(
            relative, label="discovered source path"
        )
        source = _safe_source(root, normalized, label="discovered source")
        data, digest = _read_source(source, label="discovered source")
        discovered[normalized] = {
            "path": normalized,
            "name": _frontmatter_name(
                data, label=f"discovered source {normalized}"
            ),
            "sha256": digest,
        }
    return discovered


def _runtime_policy(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    if set(value) != _RUNTIME_POLICY_KEYS:
        _fail(f"{label} must contain only tier and model_visible")
    tier = value.get("tier")
    visible = value.get("model_visible")
    if isinstance(tier, bool) or not isinstance(tier, int) or tier not in (1, 2):
        _fail(f"{label}.tier must be 1 or 2")
    if not isinstance(visible, bool):
        _fail(f"{label}.model_visible must be a boolean")
    if not visible and tier != 2:
        _fail(f"{label} may hide only a tier-2 skill")
    return {"tier": tier, "model_visible": visible}


def _registration(value: Any, *, root: Path, index: int) -> dict[str, Any]:
    label = f"registration {index}"
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    if set(value) != _REGISTRATION_KEYS:
        _fail(f"{label} must contain canonical_name, aliases, source_path, and runtime_policy")
    canonical = _validate_name(
        value.get("canonical_name"), label=f"{label}.canonical_name"
    )
    aliases = value.get("aliases")
    if not isinstance(aliases, list):
        _fail(f"{label}.aliases must be a list")
    normalized_aliases = [
        _validate_name(alias, label=f"{label}.aliases[{alias_index}]")
        for alias_index, alias in enumerate(aliases)
    ]
    if len(set(normalized_aliases)) != len(normalized_aliases):
        _fail(f"{label} contains duplicate aliases")
    source_path = _normal_relative_path(
        value.get("source_path"), label=f"{label}.source_path"
    )
    # Resolve here so an invalid registration fails before any manifest entry
    # is assembled.  The discovered map remains the authority for membership.
    _safe_source(root, source_path, label=label)
    return {
        "canonical_name": canonical,
        "aliases": sorted(normalized_aliases),
        "source_path": source_path,
        "runtime_policy": _runtime_policy(
            value.get("runtime_policy"), label=f"{label}.runtime_policy"
        ),
    }


def _check_name_collisions(entries: list[dict[str, Any]]) -> None:
    seen: dict[str, str] = {}
    for entry in entries:
        canonical = entry["canonical_name"]
        owner = f"canonical name {canonical!r}"
        if canonical in seen:
            _fail(
                f"duplicate skill name {canonical!r}: {seen[canonical]} and {owner}"
            )
        seen[canonical] = owner
        for alias in entry["aliases"]:
            owner = f"alias {alias!r} for {canonical!r}"
            if alias in seen:
                _fail(
                    f"duplicate skill name or alias {alias!r}: "
                    f"{seen[alias]} and {owner}"
                )
            seen[alias] = owner


def derive_manifest(
    root: Path | str,
    registrations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive a deterministic exposure manifest from local skill sources."""

    source_root = _root_path(root, label="source root")
    if registrations is None:
        registrations = []
    if not isinstance(registrations, list):
        _fail("registrations must be a list")

    discovered = _discover(source_root)
    parsed = [
        _registration(item, root=source_root, index=index)
        for index, item in enumerate(registrations)
    ]
    by_path: dict[str, dict[str, Any]] = {}
    for registration in parsed:
        path = registration["source_path"]
        if path not in discovered:
            _fail(f"registration source is not a discovered SKILL.md: {path}")
        if path in by_path:
            _fail(f"duplicate registration source path: {path}")
        by_path[path] = registration

    entries: list[dict[str, Any]] = []
    for path in sorted(discovered):
        source = discovered[path]
        registration = by_path.get(path)
        if registration is None:
            canonical = source["name"]
            aliases: list[str] = []
            policy = dict(DEFAULT_RUNTIME_POLICY)
        else:
            canonical = registration["canonical_name"]
            aliases = list(registration["aliases"])
            policy = dict(registration["runtime_policy"])
        entries.append(
            {
                "canonical_name": canonical,
                "aliases": aliases,
                "source": {"path": path, "sha256": source["sha256"]},
                "runtime_policy": policy,
            }
        )

    _check_name_collisions(entries)
    entries.sort(key=lambda item: (item["canonical_name"], item["source"]["path"]))
    return {"schema": MANIFEST_SCHEMA, "entries": entries}


def _validate_manifest_entry(
    value: Any, *, source_root: Path, index: int
) -> dict[str, Any]:
    label = f"manifest entry {index}"
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    for key in ("canonical_name", "aliases", "source", "runtime_policy"):
        if key not in value:
            _fail(f"{label} is missing {key}")
    canonical = _validate_name(
        value.get("canonical_name"), label=f"{label}.canonical_name"
    )
    aliases = value.get("aliases")
    if not isinstance(aliases, list):
        _fail(f"{label}.aliases must be a list")
    normalized_aliases = [
        _validate_name(alias, label=f"{label}.aliases[{alias_index}]")
        for alias_index, alias in enumerate(aliases)
    ]
    if len(set(normalized_aliases)) != len(normalized_aliases):
        _fail(f"{label} contains duplicate aliases")

    source = value.get("source")
    if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
        _fail(f"{label}.source must contain only path and sha256")
    path = _normal_relative_path(source.get("path"), label=f"{label}.source.path")
    if PurePosixPath(path).name != "SKILL.md":
        _fail(f"{label}.source.path must identify SKILL.md")
    digest = source.get("sha256")
    if not isinstance(digest, str) or _HEX_SHA256.fullmatch(digest) is None:
        _fail(f"{label}.source.sha256 must be a lowercase SHA-256 digest")
    actual_path = _safe_source(source_root, path, label=label)
    _, actual_digest = _read_source(actual_path, label=label)
    if actual_digest != digest:
        _fail(f"{label} source digest is stale: {path}")

    policy = _runtime_policy(value.get("runtime_policy"), label=f"{label}.runtime_policy")
    return {
        "canonical_name": canonical,
        "aliases": normalized_aliases,
        "source": {"path": path, "sha256": digest},
        "runtime_policy": policy,
    }


def _validated_entries(
    manifest: Any, *, source_root: Path
) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        _fail("manifest must be an object")
    schema = manifest.get("schema")
    if schema is not None and schema != MANIFEST_SCHEMA:
        _fail(f"manifest schema must be {MANIFEST_SCHEMA}")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        _fail("manifest entries must be a list")
    validated = [
        _validate_manifest_entry(item, source_root=source_root, index=index)
        for index, item in enumerate(entries)
    ]
    _check_name_collisions(validated)
    return validated


def resolve_skill(
    query: str,
    manifest: dict[str, Any],
    *,
    source_root: Path | str,
) -> dict[str, Any]:
    """Resolve one exact canonical name or alias after source revalidation."""

    if not isinstance(query, str) or not query or query != query.strip():
        _fail("skill query must be a non-empty exact string")
    root = _root_path(source_root, label="source root")
    entries = _validated_entries(manifest, source_root=root)
    for entry in entries:
        if query == entry["canonical_name"] or query in entry["aliases"]:
            return copy.deepcopy(entry)
    _fail(f"unknown skill or alias: {query!r}")


_RUNTIME_NAME = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# Generated personas that live outside the flat layout: an exact name prefix maps
# to a category directory. A caller with another layout passes its own tuple of
# (prefix, directory) pairs, or declares each ``source_path`` in the policy.
DEFAULT_FAMILIES = (("celebrity_", "celebrity"), ("mentor_", "mentor"))
GENERATED_PERSONA_DIRECTORY = "dot-skill/skills"


def _canonical_relative_source(
    name: str,
    *,
    root: Path,
    declared: str | None = None,
    families: tuple[tuple[str, str], ...] = DEFAULT_FAMILIES,
    generated_root: str = GENERATED_PERSONA_DIRECTORY,
) -> str:
    """Map a registered name to its canonical project ``SKILL.md``.

    The registration's own ``source_path`` wins when that file exists, so a
    project declares its layout instead of matching this module's fallbacks. The
    family mapping then covers generated personas at
    ``<generated_root>/<category>/<slug>/SKILL.md``; everything else is
    ``<name>/SKILL.md``. Runtime exports and projections are never consulted.
    """

    if declared is not None:
        try:
            _safe_source(root, declared, label=f"{name} declared source")
        except ExposureManifestError:
            pass
        else:
            return declared
    for prefix, category in families:
        if name.startswith(prefix) and len(name) > len(prefix):
            slug = name[len(prefix):]
            return f"{generated_root}/{category}/{slug}/SKILL.md"
    return f"{name}/SKILL.md"


def _read_policy(policy_path: Path | str) -> dict[str, Any]:
    try:
        policy = json.loads(Path(policy_path).read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        _fail(f"exposure policy is unreadable: {exc}")
    if not isinstance(policy, dict):
        _fail("exposure policy must be an object")
    schema = policy.get("schema")
    if schema is not None and schema not in POLICY_SCHEMAS:
        _fail(f"exposure policy schema is not supported: {schema!r}")
    return policy


def _policy_exclusions(
    policy: dict[str, Any], *, root: Path, taken: set[str]
) -> list[dict[str, str]]:
    """Validate the deliberate ``exclusions`` list and return it.

    An exclusion says a project skill is intentionally outside the exposure
    policy.  It must name a real ``SKILL.md`` whose frontmatter name matches,
    carry a reason, and not also be registered (or collide with an alias).
    """

    exclusions = policy.get("exclusions", [])
    if not isinstance(exclusions, list):
        _fail("exposure policy exclusions must be a list")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(exclusions):
        label = f"exclusion {index}"
        if not isinstance(item, dict) or set(item) != _EXCLUSION_KEYS:
            _fail(f"{label} must contain canonical_name, source_path, and reason")
        name = _validate_name(item.get("canonical_name"), label=f"{label}.canonical_name")
        reason = _validate_name(item.get("reason"), label=f"{label}.reason")
        if name in seen:
            _fail(f"duplicate exclusion: {name}")
        if name in taken:
            _fail(f"{label} {name!r} is also registered or an alias; choose one")
        seen.add(name)
        source_path = _normal_relative_path(
            item.get("source_path"), label=f"{label}.source_path"
        )
        source = _safe_source(root, source_path, label=label)
        data, _ = _read_source(source, label=label)
        if _frontmatter_name(data, label=label) != name:
            _fail(f"{label} source frontmatter name is not {name}")
        result.append(
            {"canonical_name": name, "source_path": source_path, "reason": reason}
        )
    return result


def policy_exclusions(
    project_root: Path | str, policy_path: Path | str
) -> list[dict[str, str]]:
    """Return the validated deliberate exclusions of an exposure policy."""

    root = _root_path(project_root, label="project skills root")
    policy = _read_policy(policy_path)
    taken: set[str] = set()
    registrations = policy.get("registrations")
    if isinstance(registrations, list):
        for item in registrations:
            if isinstance(item, dict):
                taken.add(str(item.get("canonical_name")))
                taken.update(str(a) for a in item.get("aliases") or [])
    return _policy_exclusions(policy, root=root, taken=taken)


def enumerate_skill_dirs(
    project_root: Path | str,
    *,
    generated_root: str = GENERATED_PERSONA_DIRECTORY,
) -> list[tuple[str, str]]:
    """List every runtime-exposed skill directory as ``(relative_dir, name)``.

    The universe is ``<root>/<dir>/SKILL.md`` plus the generated personas at
    ``<generated_root>/<category>/<slug>/SKILL.md``.  Symlinked directories are
    aliases of another skill, and ``SKILL.md`` files nested under a skill's own
    ``references``/``vendor``/``tools`` trees are documentation, not skills.
    A directory whose frontmatter cannot be read is listed under its directory
    name so it is never silently skipped.
    """

    root = _root_path(project_root, label="project skills root")
    patterns = ["*/SKILL.md"]
    generated = PurePosixPath(generated_root)
    if not generated.is_absolute() and ".." not in generated.parts:
        patterns.append(f"{generated.as_posix()}/*/*/SKILL.md")
    found: dict[str, str] = {}
    for pattern in patterns:
        for skill_file in root.glob(pattern):
            directory = skill_file.parent
            if directory.is_symlink() or skill_file.is_symlink():
                continue
            relative = directory.relative_to(root).as_posix()
            try:
                name = _frontmatter_name(skill_file.read_bytes(), label=relative)
            except (OSError, ExposureManifestError):
                name = directory.name
            found[relative] = name
    return sorted(found.items())


def unlisted_skills(
    project_root: Path | str,
    policy_path: Path | str,
    *,
    generated_root: str = GENERATED_PERSONA_DIRECTORY,
) -> list[str]:
    """Return skill directories that are neither registered nor excluded."""

    root = _root_path(project_root, label="project skills root")
    policy = _read_policy(policy_path)
    registrations = policy.get("registrations")
    if not isinstance(registrations, list):
        _fail("exposure policy registrations must be a list")
    listed: set[str] = set()
    for item in registrations:
        if isinstance(item, dict) and isinstance(item.get("canonical_name"), str):
            listed.add(item["canonical_name"])
    exclusions = policy.get("exclusions", [])
    if isinstance(exclusions, list):
        for item in exclusions:
            if isinstance(item, dict) and isinstance(item.get("canonical_name"), str):
                listed.add(item["canonical_name"])
    return [
        relative
        for relative, name in enumerate_skill_dirs(root, generated_root=generated_root)
        if name not in listed
    ]


def canonical_policy_manifest(
    project_root: Path | str,
    policy_path: Path | str,
    *,
    families: tuple[tuple[str, str], ...] = DEFAULT_FAMILIES,
    generated_root: str = GENERATED_PERSONA_DIRECTORY,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Derive the policy manifest directly from canonical project sources.

    Returns the manifest and each canonical name's bound source file.  This
    needs no runtime home, projection, or discovery root, so any runtime can
    resolve a startup-hidden skill by exact name.
    """

    root = _root_path(project_root, label="project skills root")
    policy = _read_policy(policy_path)
    registrations = policy.get("registrations")
    if not isinstance(registrations, list):
        _fail("exposure policy registrations must be a list")

    bound: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="skill-exposure-canonical-") as temporary:
        snapshot = Path(temporary)
        for index, registration in enumerate(registrations):
            label = f"registration {index}"
            name = registration.get("canonical_name") if isinstance(registration, dict) else None
            if not isinstance(name, str) or _RUNTIME_NAME.fullmatch(name) is None:
                _fail(f"{label} canonical_name is not a runtime name")
            if name in bound:
                _fail(f"duplicate registration canonical name: {name}")
            declared = registration.get("source_path")
            if declared is not None:
                declared = _normal_relative_path(declared, label=f"{label}.source_path")
            relative = _canonical_relative_source(
                name,
                root=root,
                declared=declared,
                families=families,
                generated_root=generated_root,
            )
            source = _safe_source(
                root, relative, label=f"{label} canonical source"
            )
            data, _ = _read_source(source, label=f"{label} canonical source")
            if _frontmatter_name(data, label=f"{label} canonical source") != name:
                _fail(f"{label} canonical source frontmatter name is not {name}")
            destination = snapshot / name / "SKILL.md"
            destination.parent.mkdir()
            destination.write_bytes(data)
            bound[name] = source
        manifest = derive_manifest(snapshot, registrations)
    taken = {entry["canonical_name"] for entry in manifest["entries"]}
    for entry in manifest["entries"]:
        taken.update(entry["aliases"])
    _policy_exclusions(policy, root=root, taken=taken)
    return manifest, bound


def resolve_canonical_skill(
    query: str,
    *,
    project_root: Path | str,
    policy_path: Path | str,
    families: tuple[tuple[str, str], ...] = DEFAULT_FAMILIES,
    generated_root: str = GENERATED_PERSONA_DIRECTORY,
) -> dict[str, Any]:
    """Resolve one exact name or alias to its canonical project source."""

    manifest, bound = canonical_policy_manifest(
        project_root,
        policy_path,
        families=families,
        generated_root=generated_root,
    )
    if not isinstance(query, str) or not query or query != query.strip():
        _fail("skill query must be a non-empty exact string")
    for entry in manifest["entries"]:
        if query == entry["canonical_name"] or query in entry["aliases"]:
            source = bound[entry["canonical_name"]]
            _, digest = _read_source(source, label="canonical source")
            if digest != entry["source"]["sha256"]:
                _fail(f"canonical source changed during resolution: {source}")
            return {
                "name": entry["canonical_name"],
                "query": query,
                "source_path": str(source),
                "source": {"path": str(source)},
                "omitted": entry["runtime_policy"]["model_visible"] is False,
            }
    _fail(f"unknown skill or alias: {query!r}")
