"""Deterministic doctrine index and on-demand retrieval (WP02 / T005-T008).

Builds a selector -> canonical-source index over the doctrine corpus and exposes
it through ``spec-kitty steer fetch``. The index is the *resolution* layer only:
it maps a selector (``directive:DIRECTIVE_030``, ``section:terminology-canon``)
to the canonical source file on disk. The body itself is retrieved from the
canonical surface -- ``spec-kitty charter context --include <selector>`` via
:func:`charter.activation.context.build_charter_context_include` -- so no
doctrine text is ever re-authored or paraphrased (NFR-003). When the engine
cannot render a resolved selector, the source file bytes are returned verbatim.

Determinism and dependency posture (C-005):

* No embedding model and no new third-party dependency -- the query backends
  use only the standard library (``sqlite3`` and ``json``).
* ``sqlite3`` **FTS5** backs keyword queries when the interpreter's SQLite is
  compiled with FTS5; a plain in-memory scan over the same entries is the
  fallback. Both backends expose the identical ``resolve``/``search`` surface.
* An unknown selector is an explicit :data:`STEER_SELECTOR_UNKNOWN` error, never
  an empty result.

The index is persisted as JSON under ``.kittify/runtime/steering/`` (gitignored
runtime state) and rebuilt when the discovered source set changes. The module
imports the ``charter`` engine lazily so importing :mod:`specify_cli.steering`
stays light.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from charter.offering.artifact_kinds import ArtifactKind

# ``src/specify_cli/`` modules are not required to declare ``__all__`` (C-007
# binds ``src/charter/`` and ``src/kernel/`` only). Declaring it here would turn
# every public name into an exported symbol the dead-code gate (#470) must find a
# caller for; the module's one cross-module entry point is ``run``, reached by
# ``specify_cli.cli.commands.steer`` as ``index.run``.

#: Stable error code emitted when a selector has no canonical source.
STEER_SELECTOR_UNKNOWN = "STEER_SELECTOR_UNKNOWN"

#: On-disk payload schema version (bump when the persisted shape changes).
INDEX_VERSION = 1

#: Gitignored runtime location for the persisted index.
_INDEX_RELATIVE = Path(".kittify") / "runtime" / "steering" / "doctrine-index.json"

#: Canonical charter bundle used to resolve ``section:<slug>`` selectors.
_CHARTER_MD_RELATIVE = Path(".kittify") / "charter" / "charter.md"

#: First top-level ``id``/``profile-id`` line of a doctrine YAML artifact.
_ID_RE = re.compile(r"^(?:profile-id|profile_id|id)\s*:\s*(?P<value>.+?)\s*$", re.MULTILINE)

#: First top-level ``when`` line (present on some artifacts), if any.
_WHEN_RE = re.compile(r"^when\s*:\s*(?P<value>.+?)\s*$", re.MULTILINE)

#: Token splitter shared by both query backends (keeps ``_`` inside a token so
#: ``DIRECTIVE_030`` stays one term, matching the FTS5 ``unicode61`` tokenizer).
_QUERY_SPLIT_RE = re.compile(r"[^0-9a-zA-Z_]+")


class SteerSelectorUnknown(LookupError):
    """Raised when a selector resolves to no canonical doctrine source.

    Carries :data:`STEER_SELECTOR_UNKNOWN` as :attr:`code` so the CLI error
    surface is machine-checkable, and never degrades to an empty result.
    """

    code = STEER_SELECTOR_UNKNOWN

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"{STEER_SELECTOR_UNKNOWN}: no canonical doctrine source for selector {selector!r}.")


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One resolved doctrine selector and its canonical source location."""

    selector: str
    source_path: str
    when: str

    def to_payload(self) -> dict[str, str]:
        """Return the JSON-persistable form of this entry."""
        return {"selector": self.selector, "source_path": self.source_path, "when": self.when}

    @classmethod
    def from_payload(cls, payload: object) -> IndexEntry | None:
        """Rebuild an entry from persisted JSON, or return ``None`` if malformed."""
        if not isinstance(payload, dict):
            return None
        selector = payload.get("selector")
        source_path = payload.get("source_path")
        when = payload.get("when")
        if not isinstance(selector, str) or not isinstance(source_path, str) or not isinstance(when, str):
            return None
        return cls(selector=selector, source_path=source_path, when=when)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """The canonical body for one resolved selector."""

    selector: str
    source_path: str
    body: str


class DoctrineIndex:
    """Shared query surface for the JSON and FTS5 backends.

    ``resolve`` performs an exact selector lookup (identical across backends);
    ``search`` performs a keyword query and may use the backend that is
    available. Subclasses set :attr:`backend_name` and implement the two
    query methods.
    """

    backend_name: str = "unknown"

    def __init__(self, entries: tuple[IndexEntry, ...]) -> None:
        self._entries = tuple(entries)
        self._by_selector = {entry.selector: entry for entry in self._entries}

    @property
    def entries(self) -> tuple[IndexEntry, ...]:
        """The indexed entries, ordered by ``(selector, source_path)``."""
        return self._entries

    def resolve(self, selector: str) -> IndexEntry | None:
        """Return the entry for *selector*, or ``None`` when it is unknown."""
        found = self._by_selector.get(selector)
        if found is not None:
            return found
        normalized = _normalize_selector(selector)
        if normalized != selector:
            return self._by_selector.get(normalized)
        return None

    def search(self, query: str) -> tuple[IndexEntry, ...]:  # pragma: no cover - overridden
        """Return entries matching *query* (keyword search); see subclasses."""
        raise NotImplementedError

    def __len__(self) -> int:
        return len(self._entries)


class JsonScanIndex(DoctrineIndex):
    """Standard-library fallback: an in-memory scan over the entry list."""

    backend_name = "json"

    def search(self, query: str) -> tuple[IndexEntry, ...]:
        terms = _query_terms(query)
        if not terms:
            return ()
        return tuple(entry for entry in self._entries if all(term in _haystack(entry) for term in terms))


class Fts5Index(DoctrineIndex):
    """SQLite FTS5 backend used when the interpreter's SQLite supports FTS5."""

    backend_name = "fts5"

    def __init__(self, entries: tuple[IndexEntry, ...]) -> None:
        super().__init__(entries)
        self._connection = sqlite3.connect(":memory:")
        self._connection.execute("CREATE VIRTUAL TABLE doc USING fts5(selector, source_path, when_)")
        self._connection.executemany(
            "INSERT INTO doc(rowid, selector, source_path, when_) VALUES (?, ?, ?, ?)",
            [(index, entry.selector, entry.source_path, entry.when) for index, entry in enumerate(self._entries)],
        )
        self._rows = dict(enumerate(self._entries))

    def search(self, query: str) -> tuple[IndexEntry, ...]:
        expression = _match_expression(query)
        if expression is None:
            return ()
        try:
            rows = self._connection.execute("SELECT rowid FROM doc WHERE doc MATCH ? ORDER BY rowid", (expression,)).fetchall()
        except sqlite3.OperationalError:
            return ()
        return tuple(self._rows[row[0]] for row in rows)


def fts5_available() -> bool:
    """Return whether the interpreter's SQLite module was compiled with FTS5."""
    try:
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        finally:
            connection.close()
    except sqlite3.OperationalError:
        return False
    return True


def index_path(repo_root: Path) -> Path:
    """Return the canonical on-disk path of the persisted index."""
    return repo_root / _INDEX_RELATIVE


@dataclass(frozen=True, slots=True)
class _ScanPlan:
    """Discovered source set plus the fingerprint that identifies it."""

    artifact_paths: tuple[tuple[str, Path], ...]
    charter_path: Path | None
    fingerprint: str


def build_entries(repo_root: Path) -> tuple[IndexEntry, ...]:
    """Scan the canonical doctrine roots and return the sorted index entries.

    Roots scanned, highest precedence first: the project overlay
    (``.kittify/doctrine/``), the configured org packs, then the shipped
    built-in pack. A selector defined in more than one tier resolves to the
    first (highest-precedence) definition. ``section:<slug>`` entries come from
    the engine's registered charter sections.
    """
    plan = _plan_sources(repo_root)
    return _entries_from_plan(plan)


def build_index(
    repo_root: Path,
    *,
    force: bool = False,
    backend: Literal["auto", "json", "fts5"] = "auto",
) -> DoctrineIndex:
    """Return a queryable index, rebuilding and re-persisting when stale.

    A persisted index whose source fingerprint still matches is reused unless
    *force* is set. *backend* selects the query backend; ``"auto"`` prefers
    FTS5 and falls back to the JSON scan when FTS5 is unavailable.
    """
    plan = _plan_sources(repo_root)
    entries = None if force else _load_cached(index_path(repo_root), plan.fingerprint)
    if entries is None:
        entries = build_entries(repo_root)
        _persist(index_path(repo_root), plan.fingerprint, entries)
    return _make_index(entries, backend=backend)


def _make_index(entries: tuple[IndexEntry, ...], *, backend: Literal["auto", "json", "fts5"] = "auto") -> DoctrineIndex:
    if backend == "json":
        return JsonScanIndex(entries)
    if backend == "fts5":
        if not fts5_available():
            raise RuntimeError("FTS5 backend requested but the interpreter's SQLite lacks FTS5 support.")
        return Fts5Index(entries)
    return Fts5Index(entries) if fts5_available() else JsonScanIndex(entries)


def canonical_source_text(repo_root: Path, entry: IndexEntry) -> str:
    """Return the canonical source file for *entry*, verbatim (no paraphrase)."""
    path = Path(entry.source_path)
    if not path.is_absolute():
        path = repo_root / path
    return path.read_text(encoding="utf-8")


def fetch(repo_root: Path, selector: str, *, index: DoctrineIndex | None = None) -> FetchResult:
    """Resolve *selector* and return its canonical body.

    Raises :class:`SteerSelectorUnknown` when the selector has no canonical
    source; an unknown selector is never an empty result.
    """
    active_index = index if index is not None else build_index(repo_root)
    entry = active_index.resolve(selector)
    if entry is None:
        raise SteerSelectorUnknown(selector)
    return FetchResult(
        selector=entry.selector,
        source_path=entry.source_path,
        body=_canonical_body(repo_root, entry),
    )


def run(selector: str, *, json_output: bool = False) -> None:
    """CLI entry point for ``spec-kitty steer fetch <selector>`` (WP01 lazy import)."""
    import typer

    repo_root = _default_repo_root()
    try:
        result = fetch(repo_root, selector)
    except SteerSelectorUnknown as exc:
        _emit_unknown(exc, json_output=json_output)
        raise typer.Exit(code=1) from exc
    if json_output:
        print(json.dumps({"selector": result.selector, "source_path": result.source_path, "body": result.body}, indent=2))
    else:
        print(result.body)


# ---------------------------------------------------------------------------
# Body resolution
# ---------------------------------------------------------------------------


def _canonical_body(repo_root: Path, entry: IndexEntry) -> str:
    """Return the canonical body for *entry*.

    The engine surface is the canonical source of a rendered body
    (``charter context --include``); the raw source file is the fallback when
    the engine cannot render the selector (e.g. an engine-independent project
    overlay).
    """
    engine_body = _engine_body(repo_root, entry.selector)
    if engine_body:
        return engine_body
    return canonical_source_text(repo_root, entry)


def _engine_body(repo_root: Path, selector: str) -> str | None:
    """Render *selector* through the engine, or return ``None`` when it cannot."""
    try:
        from charter.activation.context import build_charter_context_include
    except ImportError:
        return None
    try:
        return build_charter_context_include(repo_root, selector, org_root=_first_org_root(repo_root))
    except (ValueError, OSError):
        return None


def _first_org_root(repo_root: Path) -> Path | None:
    roots = _existing_org_roots(repo_root)
    return roots[0] if roots else None


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------


def _plan_sources(repo_root: Path) -> _ScanPlan:
    artifact_paths = _artifact_paths(repo_root)
    charter = repo_root / _CHARTER_MD_RELATIVE
    charter_path = charter if charter.is_file() else None
    watched = [path for _, path in artifact_paths]
    if charter_path is not None:
        watched.append(charter_path)
    return _ScanPlan(artifact_paths, charter_path, _fingerprint(watched))


def _artifact_paths(repo_root: Path) -> tuple[tuple[str, Path], ...]:
    """Discover artifact files across the project, org and built-in tiers.

    Ordering is precedence order (project first, built-in last) so a
    first-wins dedupe keeps the highest-precedence definition.
    """
    discovered: list[tuple[str, Path]] = []
    for kind in _content_kinds():
        for directory in _artifact_dirs(repo_root, kind):
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob(kind.glob_pattern)):
                discovered.append((kind.value, path))
    return tuple(discovered)


def _content_kinds() -> tuple[ArtifactKind, ...]:
    from charter.offering.artifact_kinds import ArtifactKind

    return tuple(kind for kind in ArtifactKind if kind.has_built_in_content_dir and kind.glob_pattern)


def _artifact_dirs(repo_root: Path, kind: ArtifactKind) -> tuple[Path, ...]:
    from charter.offering.artifact_kinds import PROJECT_KIND_DIRS
    from charter.offering.pack_paths import BuiltInContentDirNotAvailable, PackRootNotFound, built_in_dir

    directories = [repo_root / ".kittify" / "doctrine" / PROJECT_KIND_DIRS[kind]]
    directories.extend(org / kind.plural for org in _existing_org_roots(repo_root))
    with contextlib.suppress(PackRootNotFound, BuiltInContentDirNotAvailable):
        directories.append(built_in_dir(kind))
    return tuple(directories)


def _existing_org_roots(repo_root: Path) -> tuple[Path, ...]:
    from charter.offering.drg.org_pack_config import resolve_existing_org_roots

    return tuple(resolve_existing_org_roots(repo_root))


def _entries_from_plan(plan: _ScanPlan) -> tuple[IndexEntry, ...]:
    by_selector: dict[str, IndexEntry] = {}
    for kind_value, path in plan.artifact_paths:
        entry = _artifact_entry(kind_value, path)
        if entry is not None:
            by_selector.setdefault(entry.selector, entry)
    for entry in _section_entries(plan.charter_path):
        by_selector.setdefault(entry.selector, entry)
    return tuple(sorted(by_selector.values(), key=lambda entry: (entry.selector, entry.source_path)))


def _artifact_entry(kind_value: str, path: Path) -> IndexEntry | None:
    """Parse one artifact file into an entry, or ``None`` when it has no id.

    The id is the artifact's own top-level ``id``/``profile-id`` field; a file
    without one is not a resolvable selector and is skipped rather than given a
    guessed identity.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    identifier = _first_match(_ID_RE, text)
    if not identifier:
        return None
    return IndexEntry(
        selector=f"{kind_value}:{identifier}",
        source_path=str(path),
        when=_first_match(_WHEN_RE, text) or "",
    )


def _section_entries(charter_path: Path | None) -> tuple[IndexEntry, ...]:
    if charter_path is None:
        return ()
    from charter.activation.context_renderers.section_bodies import (
        ACTION_CRITICAL_SECTIONS,
        critical_section_selector,
        critical_section_when_clause,
    )

    headings = sorted({heading for headings in ACTION_CRITICAL_SECTIONS.values() for heading in headings})
    return tuple(
        IndexEntry(
            selector=critical_section_selector(heading),
            source_path=str(charter_path),
            when=critical_section_when_clause(heading),
        )
        for heading in headings
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _fingerprint(paths: list[Path]) -> str:
    """Return a content-independent fingerprint of the discovered source set.

    The fingerprint is a SHA-256 over each source path's size and mtime, so an
    added, removed or edited source rebuilds the index (T005 step 3). It routes
    through the canonical :func:`charter.hasher.hash_content` seam rather than a
    second raw hash implementation.
    """
    from charter.hasher import hash_content

    lines = []
    for path in sorted(set(paths), key=str):
        try:
            stat = path.stat()
        except OSError:
            continue
        lines.append(f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}")
    return hash_content("\n".join(lines))


def _load_cached(path: Path, fingerprint: str) -> tuple[IndexEntry, ...] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != INDEX_VERSION:
        return None
    if payload.get("fingerprint") != fingerprint:
        return None
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return None
    entries = tuple(entry for entry in (IndexEntry.from_payload(item) for item in raw_entries) if entry is not None)
    if not entries:
        return None
    return entries


def _persist(path: Path, fingerprint: str, entries: tuple[IndexEntry, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": INDEX_VERSION,
        "fingerprint": fingerprint,
        "entries": [entry.to_payload() for entry in entries],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _query_terms(query: str) -> tuple[str, ...]:
    return tuple(term for term in _QUERY_SPLIT_RE.split(query.lower()) if term)


def _match_expression(query: str) -> str | None:
    terms = _query_terms(query)
    if not terms:
        return None
    return " AND ".join(f'"{term}"' for term in terms)


def _haystack(entry: IndexEntry) -> str:
    return f"{entry.selector} {entry.when} {entry.source_path}".lower()


def _normalize_selector(selector: str) -> str:
    """Normalize a hyphenated artifact kind to its canonical underscore form."""
    kind, separator, identifier = selector.partition(":")
    if not separator or not kind or not identifier:
        return selector
    from charter.offering.artifact_kinds import ArtifactKind

    try:
        canonical_kind = ArtifactKind.from_operator_token(kind).value
    except ValueError:
        return selector
    return f"{canonical_kind}:{identifier}"


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return _strip_quotes(match.group("value"))


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _default_repo_root() -> Path:
    from specify_cli.task_utils import find_repo_root

    return find_repo_root()


def _emit_unknown(exc: SteerSelectorUnknown, *, json_output: bool) -> None:
    message = str(exc)
    if json_output:
        payload = {"success": False, "error": STEER_SELECTOR_UNKNOWN, "selector": exc.selector, "message": message}
        print(json.dumps(payload), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)
