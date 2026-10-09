# Coding-agent rules (Markdown encoding)

This file is the "status quo" encoding: every rule is written as prose under a
heading, with a rationale, exactly as a large `AGENTS.md` would carry it. All eight
rules are present. Compliance is advisory.

## R1 — Never commit directly to `main`

`main` is the integration branch. Never push to `main`: create a topic branch from the
current `main`, open a pull request targeting `main`, and let repository review and
branch-protection settings enforce the merge. Direct pushes bypass the review gate and
can publish unreviewed or broken work. Enforcement: advisory.

## R2 — Say "Mission", never "feature"

The canonical product term is **Mission** (plural: **Missions**). The words `feature`
and `features` are prohibited in canonical, operator, and user-facing language when
they refer to the domain object. Terminology drift makes the domain model ambiguous.
Enforcement: advisory (review).

## R3 — No blanket `# noqa`

A lint suppression must name the specific rule code it suppresses and carry a short
rationale. A bare `# noqa` that suppresses everything is not allowed, because it hides
new findings as well as the one intended. Enforcement: advisory.

## R4 — One trailing newline, no trailing whitespace

Every source file ends with exactly one trailing newline and contains no line with
trailing whitespace. This avoids noisy diffs and toolchain churn. Enforcement:
advisory.

## R5 — Conventional Commits

Commit subjects follow `type(scope): subject`, where `type` is one of the repository's
allowed types (for example `feat`, `fix`, `docs`, `chore`). A machine-readable history
lets tooling group and validate changes. Enforcement: advisory.

## R6 — Format and lint before push

Run `ruff format --check .` and `ruff check .` before pushing; both must pass.
Formatting is a separate gate from linting. Enforcement: advisory.

## R7 — Prefer a durable fix over a shim

When a structural cause produces a defect, fix the structure rather than hiding the
symptom behind a shim. If a shim is genuinely unavoidable, say why in the change.
Shims accumulate and rot. Enforcement: judgment.

## R8 — Read the charter before planning

Read `.kittify/charter/charter.md` before planning or changing code; it is the binding
governance document and carries rules not repeated elsewhere. Enforcement: process.
