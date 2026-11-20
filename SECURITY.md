# Security policy

## Supported versions

Security fixes go into the latest release. Upgrade before reporting, in case the problem is
already fixed.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Older | No |

## Reporting a vulnerability

Report it privately, not in a public issue: use the
[Report a vulnerability](https://github.com/elfenomenokim/skill-exposure-manifest/security/advisories/new)
form on the repository's Security tab.

Include the policy entry, the tree layout, the version, and what an attacker could do with the result.
You get a reply within a few days.

## In scope

- A resolved `source_path` that leaves the declared root, for example through a symlink or a `..` segment.
- A manifest entry whose recorded digest passes although the file changed.
- A name or alias collision that resolves to the wrong skill.
- A file read outside the source root that the caller did not ask for.
- An input that makes derivation read something other than a regular `SKILL.md`.

## Not a vulnerability

- A resolution refusing because the source changed. That is the intended behaviour; re-derive the manifest.
- A policy that hides a tier-2 skill. That is configuration.
- Resolution being slow on a large tree. Every resolve re-reads the bound bytes by design; derive once and reuse.

## Disclosure

Once a fix is released, the advisory is published with credit to the reporter unless they prefer
otherwise.
