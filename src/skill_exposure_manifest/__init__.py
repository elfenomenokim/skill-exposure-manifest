"""Content-bound skill exposure manifests.

The manifest binds each skill name to a source path and that source's SHA-256.
Resolution accepts one exact name or alias, re-reads the bound bytes, and refuses
a stale digest, a duplicate name, a symlink, or a path outside the root.
"""

from .core import (
    DEFAULT_FAMILIES,
    DEFAULT_RUNTIME_POLICY,
    GENERATED_PERSONA_DIRECTORY,
    MANIFEST_SCHEMA,
    POLICY_SCHEMAS,
    ExposureManifestError,
    canonical_policy_manifest,
    derive_manifest,
    enumerate_skill_dirs,
    policy_exclusions,
    unlisted_skills,
    resolve_canonical_skill,
    resolve_skill,
)

__all__ = [
    "DEFAULT_FAMILIES",
    "DEFAULT_RUNTIME_POLICY",
    "GENERATED_PERSONA_DIRECTORY",
    "MANIFEST_SCHEMA",
    "POLICY_SCHEMAS",
    "ExposureManifestError",
    "canonical_policy_manifest",
    "derive_manifest",
    "enumerate_skill_dirs",
    "policy_exclusions",
    "unlisted_skills",
    "resolve_canonical_skill",
    "resolve_skill",
]

__version__ = "0.2.0"
