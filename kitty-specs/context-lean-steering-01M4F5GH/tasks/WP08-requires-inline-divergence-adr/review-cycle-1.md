---
affected_files: []
cycle_number: 1
mission_slug: context-lean-steering-01M4F5GH
reproduction_command:
reviewed_at: '2026-10-09T03:11:51Z'
reviewer_agent: opencode
wp_id: WP08
---

# WP08 review feedback (review-1)

**Verdict:** Changes requested — one blocking defect. The ADR content itself is
correct and complete; the deliverable fails a repo-enforced docs gate.

## Issue 1 (BLOCKING) — ADR `description` exceeds the enforced 50–180 char SEO band

`docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md` frontmatter
`description` is **327 characters**. The repository caps published-page
descriptions at **180** (`scripts/docs/description_length_check.py`,
`MAX_DESCRIPTION_LENGTH = 180`), and the historical `docs/adr/` exemption from
this gate was **retired** — ADRs are in scope like every other published page
(`docs/docfx.json` includes `adr/**.md`; see the "Historical note — the retired
`docs/adr/` exclusion" in `scripts/docs/description_length_check.py:94-120`).

This turns the docs gates red for this WP (the only violation in the whole
631-page corpus):

```
tests/docs/test_docs_seo.py::test_published_pages_have_title_and_description[docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md]
  AssertionError: ... description length is off: 327 (band 50-180)

tests/docs/test_description_length_gate.py::test_live_tree_is_clean
  AssertionError: 1 description violation(s) across 631 published page(s):
      TOO_LONG docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md
```

The file is absent at the WP base (`d60f0a3295b7`), so this red is introduced by
WP08; it is not a pre-existing failure.

### Fix

Shorten the frontmatter `description` to **50–180 characters** (it must also stay
unique across the corpus). The long form belongs in the `## Context and Problem
Statement` body, not the metadata field. For example:

```yaml
description: 'Inside the ≤2 KB steering capsule, `requires` doctrine ships as `{selector, when}` fetch pointers rather than inline bodies, partially superseding ADR 2026-07-28-1.'
```

Then re-run and paste the results into the WP:

```
.venv/bin/python -m scripts.docs.description_length_check --strict
.venv/bin/python -m pytest tests/docs/test_docs_seo.py tests/docs/test_description_length_gate.py -q
```

(Note: `baseline-tests.json` for this WP records `total: 0` — the docs blast
radius was not exercised. The two commands above are the required coverage for a
docs/ADR deliverable.)

## What passed (no change required)

Independently verified against `git show bdcb50404` and the ADR text:

- **ADR exists and follows repo ADR shape** — PASS. `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md`
  has frontmatter (`title`/`description`/`status`/`date`, parses) and body
  sections Status, Date, Deciders, Technical Story, Reader, Context and Problem
  Statement, Decision, Supersession boundary, Rationale, Alternatives, Divergence,
  Consequences, References.
- **Decision stated + mission/operator-decision references** — PASS. States fetch
  `{selector, when}` pointers, on-demand retrieval via
  `charter context --include`; cites mission `context-lean-steering-01M4F5GH`, the
  2026-10-09 operator decision, and Decision Moments `01M4F5S7X15RATYMKWZCAV8CWN`
  and `01M4F6770GPKE0HZ3CCTN906P9`.
- **Supersession boundary precise** — PASS. Supersedes exactly "Decision item 2 of
  ADR 2026-07-28-1 — the requires-eager inline guarantee — and only under a
  budget-constrained capsule"; explicitly preserves Decision items 1, 3, 4, 5,
  the default-cadence ordering constraint, and the "what this ADR does not
  decide" items. "What still holds" names fetchability (nothing omitted),
  link-only `suggests`, and canonical retrieval (no paraphrase). Matches the
  actual clauses in `docs/adr/3.x/2026-07-28-1-...md`.
- **"Divergence" section** — PASS. Names it "the mission's single documented
  divergence", cites operator decision (2026-10-09), constraint `C-002`, and
  cross-references `plan.md` §Complexity Tracking (`Why Needed` /
  `Simpler Alternative Rejected Because`).
- **No source file changed** — PASS. Commit `bdcb50404` touches only three docs
  files; no `src/` path. The two extra files
  (`docs/adr/4.x/index.md`, `docs/development/page-inventory.yaml`) are the
  freshness-gate-required ADR index + inventory registration; the inventory is
  byte-identical to a fresh generation and
  `PYTHONPATH=. python -m scripts.docs.freshen_adr_inventory --all --check`
  reports `clean`.
