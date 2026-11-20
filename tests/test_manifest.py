"""Package-local contract tests.

Every case builds its own fixture tree and policy inside a pytest temporary
directory, so this suite runs from the exported package alone. The behaviours
covered are the ones the README promises: exact names and aliases, a stale
digest, a symlink, a path escape, an invisible combination, the exclusion list
and the unlisted-skill check.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from skill_exposure_manifest import (
    ExposureManifestError,
    canonical_policy_manifest,
    derive_manifest,
    policy_exclusions,
    resolve_canonical_skill,
    resolve_skill,
    unlisted_skills,
)


def write_skill(root: Path, directory: str, name: str, body: str = "body\n") -> str:
    """Write one fixture SKILL.md and return its POSIX path below ``root``."""

    path = root / directory / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: fixture\n---\n{body}", encoding="utf-8"
    )
    return path.relative_to(root).as_posix()


def registration(
    name: str,
    source_path: str,
    *,
    aliases: tuple[str, ...] = (),
    tier: int = 1,
    model_visible: bool = True,
) -> dict:
    return {
        "canonical_name": name,
        "aliases": list(aliases),
        "source_path": source_path,
        "runtime_policy": {"tier": tier, "model_visible": model_visible},
    }


def write_policy(
    root: Path,
    registrations: list[dict],
    exclusions: list[dict] | None = None,
    *,
    schema: str = "cch-skill-exposure-policy/2",
) -> Path:
    path = root / "policy.json"
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "registrations": registrations,
                "exclusions": exclusions or [],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


def test_manifest_binds_name_alias_path_hash_and_policy(skills: Path) -> None:
    source = write_skill(skills, "alpha", "alpha", body="canonical source\n")
    manifest = derive_manifest(
        skills, [registration("alpha", source, aliases=("a", "alpha-old"))]
    )

    assert [entry["canonical_name"] for entry in manifest["entries"]] == ["alpha"]
    entry = manifest["entries"][0]
    assert entry["aliases"] == ["a", "alpha-old"]
    assert entry["source"]["path"] == source
    assert entry["source"]["sha256"] == hashlib.sha256(
        (skills / source).read_bytes()
    ).hexdigest()
    assert entry["runtime_policy"] == {"tier": 1, "model_visible": True}


def test_resolve_accepts_exact_name_and_alias_only(skills: Path) -> None:
    source = write_skill(skills, "alpha", "alpha")
    manifest = derive_manifest(skills, [registration("alpha", source, aliases=("a",))])

    assert resolve_skill("alpha", manifest, source_root=skills)["canonical_name"] == "alpha"
    assert resolve_skill("a", manifest, source_root=skills)["canonical_name"] == "alpha"
    for query in ("Alpha", "ALPHA", "alp", "alpha-helper", " alph"):
        with pytest.raises(ExposureManifestError):
            resolve_skill(query, manifest, source_root=skills)


def test_unregistered_source_is_model_visible_by_default(skills: Path) -> None:
    write_skill(skills, "open", "open-skill")
    manifest = derive_manifest(skills)

    entry = manifest["entries"][0]
    assert entry["canonical_name"] == "open-skill"
    assert entry["source"]["path"] == "open/SKILL.md"
    assert entry["runtime_policy"]["model_visible"] is True
    assert entry["runtime_policy"]["tier"] == 1


def test_tier_two_can_be_hidden_and_tier_one_cannot(skills: Path) -> None:
    source = write_skill(skills, "heavy", "heavy-skill")
    manifest = derive_manifest(
        skills, [registration("heavy-skill", source, tier=2, model_visible=False)]
    )
    assert manifest["entries"][0]["runtime_policy"] == {"tier": 2, "model_visible": False}

    with pytest.raises(ExposureManifestError):
        derive_manifest(skills, [registration("heavy-skill", source, model_visible=False)])


def test_duplicate_names_and_aliases_fail_closed(skills: Path) -> None:
    first = write_skill(skills, "one", "one")
    second = write_skill(skills, "two", "two")
    cases = {
        "duplicate canonical": [
            registration("same", first),
            registration("same", second),
        ],
        "duplicate alias": [
            registration("one", first, aliases=("shared",)),
            registration("two", second, aliases=("shared",)),
        ],
        "alias over a canonical": [
            registration("one", first),
            registration("two", second, aliases=("one",)),
        ],
    }
    for label, registrations in cases.items():
        with pytest.raises(ExposureManifestError):
            derive_manifest(skills, registrations)
        assert label


def test_stale_source_digest_fails_closed(skills: Path) -> None:
    source = write_skill(skills, "alpha", "alpha", body="v1\n")
    manifest = derive_manifest(skills, [registration("alpha", source)])
    (skills / source).write_text(
        "---\nname: alpha\ndescription: fixture\n---\nv2\n", encoding="utf-8"
    )

    with pytest.raises(ExposureManifestError, match="digest is stale"):
        resolve_skill("alpha", manifest, source_root=skills)


def test_symlinked_source_is_refused(skills: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: outside\ndescription: fixture\n---\n", encoding="utf-8"
    )
    (skills / "linked").mkdir()
    try:
        os.symlink(outside / "SKILL.md", skills / "linked" / "SKILL.md")
    except (OSError, NotImplementedError) as error:  # Windows without symlink rights
        pytest.skip(f"this host cannot create a symlink: {error}")

    with pytest.raises(ExposureManifestError, match="symlink"):
        derive_manifest(skills)


def test_path_escape_is_refused_before_resolution(skills: Path) -> None:
    inside = write_skill(skills, "inside", "inside")
    for escaped in ("../outside/SKILL.md", "/etc/SKILL.md", "alpha\\SKILL.md"):
        with pytest.raises(ExposureManifestError):
            derive_manifest(skills, [registration("inside", inside), registration("x", escaped)])


def test_resolution_is_read_only(skills: Path) -> None:
    source = write_skill(skills, "alpha", "alpha")
    manifest = derive_manifest(skills, [registration("alpha", source)])
    before = {path.name: path.read_bytes() for path in (skills / "alpha").iterdir()}

    resolve_skill("alpha", manifest, source_root=skills)

    assert {path.name: path.read_bytes() for path in (skills / "alpha").iterdir()} == before


def test_exclusions_are_validated(skills: Path) -> None:
    alpha = write_skill(skills, "alpha", "alpha")
    beta = write_skill(skills, "beta", "beta")
    registered = [registration("alpha", alpha)]
    good = [{"canonical_name": "beta", "source_path": beta, "reason": "owner decision"}]

    policy = write_policy(skills, registered, good)
    assert policy_exclusions(skills, policy) == [
        {"canonical_name": "beta", "source_path": beta, "reason": "owner decision"}
    ]
    canonical_policy_manifest(skills, policy)

    cases = {
        "also registered": [{"canonical_name": "alpha", "source_path": alpha, "reason": "x"}],
        "missing source": [{"canonical_name": "ghost", "source_path": "ghost/SKILL.md", "reason": "x"}],
        "no reason": [{"canonical_name": "beta", "source_path": beta}],
        "name mismatch": [{"canonical_name": "beta", "source_path": alpha, "reason": "x"}],
        "duplicate": [good[0], good[0]],
    }
    for label, exclusions in cases.items():
        with pytest.raises(ExposureManifestError):
            canonical_policy_manifest(skills, write_policy(skills, registered, exclusions))
        assert label


def test_unlisted_skills_lists_what_the_policy_ignores(skills: Path) -> None:
    alpha = write_skill(skills, "alpha", "alpha")
    beta = write_skill(skills, "beta", "beta")
    write_skill(skills, "gamma", "gamma")
    write_skill(skills, "dot-skill/skills/celebrity/rubner", "celebrity_rubner")
    # A SKILL.md nested in a skill's own references tree is documentation, not a skill.
    write_skill(skills, "alpha/references/sample", "sample")
    policy = write_policy(
        skills,
        [registration("alpha", alpha)],
        [{"canonical_name": "beta", "source_path": beta, "reason": "owner decision"}],
    )

    assert unlisted_skills(skills, policy) == ["dot-skill/skills/celebrity/rubner", "gamma"]


def test_policy_manifest_resolves_aliases_from_canonical_sources(skills: Path) -> None:
    alpha = write_skill(skills, "alpha", "alpha", body="canonical\n")
    beta = write_skill(skills, "beta", "beta")
    policy = write_policy(
        skills,
        [registration("alpha", alpha, aliases=("a",))],
        [{"canonical_name": "beta", "source_path": beta, "reason": "owner decision"}],
    )

    manifest, bound = canonical_policy_manifest(skills, policy)
    assert [entry["canonical_name"] for entry in manifest["entries"]] == ["alpha"]
    assert bound["alpha"] == skills / alpha

    resolved = resolve_canonical_skill("a", project_root=skills, policy_path=policy)
    assert resolved["name"] == "alpha"
    assert resolved["query"] == "a"
    assert resolved["omitted"] is False
    assert Path(resolved["source_path"]) == (skills / alpha).resolve()

    with pytest.raises(ExposureManifestError):
        resolve_canonical_skill("A", project_root=skills, policy_path=policy)


def test_policy_schema_one_still_reads(skills: Path) -> None:
    alpha = write_skill(skills, "alpha", "alpha")
    policy = write_policy(
        skills, [registration("alpha", alpha)], schema="cch-skill-exposure-policy/1"
    )
    assert unlisted_skills(skills, policy) == []

    unsupported = write_policy(
        skills, [registration("alpha", alpha)], schema="cch-skill-exposure-policy/9"
    )
    with pytest.raises(ExposureManifestError, match="schema is not supported"):
        unlisted_skills(skills, unsupported)
