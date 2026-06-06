from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import schema as s
from .models import (
    ProjectData, ExtractedSemantic, ExtractedFinding, InProjectLink, GlobalLink,
    SemanticMergeResult, FindingMergeResult,
)
from .taxonomy import all_defi_categories, all_taxonomy_entries, coerce_defi_category, resolve_taxonomy_entry


def sqlite_path_from_url(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    path = db_url.removeprefix("sqlite:///")
    if not path or path == ":memory":
        return None
    return Path(path).expanduser().resolve()


def describe_db_url(db_url: str) -> str:
    path = sqlite_path_from_url(db_url)
    if path is None:
        return db_url
    return f"{db_url} ({path})"


def engine_from_url(db_url: str) -> Engine:
    if db_url.startswith("sqlite:///"):
        path = db_url.removeprefix("sqlite:///")
        if path and path != ":memory":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url, future=True)
    if db_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
    return engine


def init_db(db_url: str) -> None:
    engine = engine_from_url(db_url)
    s.Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        seed_categories(session)
        seed_finding_categories(session)


def seed_categories(session: Session) -> None:
    existing = {row[0] for row in session.execute(select(s.Category.name)).all()}
    for cat in all_defi_categories():
        if cat.value not in existing:
            session.add(s.Category(name=cat.value))


def seed_finding_categories(session: Session) -> None:
    existing = {(row[0], row[1]) for row in session.execute(select(s.FindingCategory.category, s.FindingCategory.name)).all()}
    for entry in all_taxonomy_entries():
        key = (entry.category.value, entry.subcategory)
        if key not in existing:
            session.add(s.FindingCategory(category=entry.category.value, name=entry.subcategory, description=entry.description))


class HistoricalDatabase:
    def __init__(self, db_url: str):
        self.engine = engine_from_url(db_url)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def init(self) -> None:
        s.Base.metadata.create_all(self.engine)
        with self.Session() as session, session.begin():
            seed_categories(session); seed_finding_categories(session)

    @contextmanager
    def session(self):
        with self.Session() as session:
            yield session

    def is_project_completed(self, platform_id_or_name: str) -> bool:
        with self.Session() as session:
            q = select(s.Project).outerjoin(s.ProjectPlatform, s.ProjectPlatform.project_id == s.Project.id).where(
                (s.Project.name == platform_id_or_name) | (s.ProjectPlatform.platform_id == platform_id_or_name)
            ).where(s.Project.status == "completed")
            return session.scalar(q) is not None

    def list_projects(self) -> list[tuple[int, str, str | None, str]]:
        with self.Session() as session:
            rows = session.execute(select(s.Project.id, s.Project.name, s.ProjectPlatform.platform_id, s.Project.status).outerjoin(s.ProjectPlatform)).all()
            return [(a,b,c,d) for a,b,c,d in rows]

    def counts(self) -> dict[str, int]:
        tables = {
            "projects": s.Project,
            "semantics": s.SemanticNode,
            "semantic_functions": s.SemanticFunction,
            "findings": s.AuditFinding,
            "semantic_finding_links": s.SemanticFindingLink,
        }
        with self.Session() as session:
            return {name: int(session.scalar(select(func.count()).select_from(model)) or 0) for name, model in tables.items()}

    def list_semantics(self, project: str | None = None) -> list[s.SemanticNode]:
        with self.Session() as session:
            q = select(s.SemanticNode)
            if project:
                q = q.join(s.ProjectSemantic, s.ProjectSemantic.semantic_node_id == s.SemanticNode.id).join(s.Project, s.Project.id == s.ProjectSemantic.project_id).outerjoin(s.ProjectPlatform, s.ProjectPlatform.project_id == s.Project.id).where((s.Project.name == project) | (s.ProjectPlatform.platform_id == project))
            return list(session.scalars(q).all())

    def search_semantics(self, keyword: str) -> list[s.SemanticNode]:
        like = f"%{keyword}%"
        with self.Session() as session:
            return list(session.scalars(select(s.SemanticNode).where((s.SemanticNode.name.like(like)) | (s.SemanticNode.definition.like(like)) | (s.SemanticNode.description.like(like)))).all())

    def canonical_semantics_with_children_for_categories(self, categories: Iterable[str]) -> list[dict]:
        cats = [coerce_defi_category(c).value for c in categories]
        with self.Session() as session:
            merged_from = select(s.SemanticMerge.from_semantic_id)
            nodes = session.scalars(select(s.SemanticNode).where(~s.SemanticNode.id.in_(merged_from)).where(s.SemanticNode.category.in_(cats) if cats else True)).all()
            return [self._semantic_with_children(session, n) for n in nodes]

    def canonical_findings_with_children_for_categories(self, categories: Iterable[str]) -> list[dict]:
        with self.Session() as session:
            merged_from = select(s.FindingMerge.from_finding_id)
            nodes = session.scalars(select(s.AuditFinding).where(~s.AuditFinding.id.in_(merged_from))).all()
            return [self._finding_with_children(session, n) for n in nodes]

    def _semantic_with_children(self, session: Session, node: s.SemanticNode) -> dict:
        children = session.scalars(select(s.SemanticNode).join(s.SemanticMerge, s.SemanticMerge.from_semantic_id == s.SemanticNode.id).where(s.SemanticMerge.to_semantic_id == node.id)).all()
        return {"id": node.id, "name": node.name, "category": node.category, "definition": node.definition, "description": node.description, "children": [{"id": c.id, "name": c.name, "description": c.description} for c in children]}

    def _finding_with_children(self, session: Session, node: s.AuditFinding) -> dict:
        children = session.scalars(select(s.AuditFinding).join(s.FindingMerge, s.FindingMerge.from_finding_id == s.AuditFinding.id).where(s.FindingMerge.to_finding_id == node.id)).all()
        return {"id": node.id, "title": node.title, "severity": node.severity, "root_cause": node.root_cause, "description": node.description, "children": [{"id": c.id, "title": c.title, "description": c.description} for c in children]}

    def resolve_semantic_canonical(self, semantic_id: int) -> list[int]:
        with self.Session() as session:
            targets = session.scalars(select(s.SemanticMerge.to_semantic_id).where(s.SemanticMerge.from_semantic_id == semantic_id)).all()
            return list(targets) or [semantic_id]

    def resolve_finding_canonical(self, finding_id: int) -> list[int]:
        with self.Session() as session:
            targets = session.scalars(select(s.FindingMerge.to_finding_id).where(s.FindingMerge.from_finding_id == finding_id)).all()
            return list(targets) or [finding_id]

    def list_pending_findings_for_linking(self) -> list[s.AuditFinding]:
        with self.Session() as session:
            linked = select(s.FindingLinkStatus.audit_finding_id)
            merged = select(s.FindingMerge.from_finding_id)
            return list(session.scalars(select(s.AuditFinding).where(~s.AuditFinding.id.in_(linked)).where(~s.AuditFinding.id.in_(merged))).all())

    def list_all_canonical_semantics(self) -> list[s.SemanticNode]:
        with self.Session() as session:
            merged = select(s.SemanticMerge.from_semantic_id)
            return list(session.scalars(select(s.SemanticNode).where(~s.SemanticNode.id.in_(merged))).all())

    def append_semantic_finding_links(self, edges: list[GlobalLink]) -> None:
        with self.Session() as session, session.begin():
            for e in edges:
                if session.get(s.SemanticFindingLink, {"semantic_node_id": e.semantic_id, "audit_finding_id": e.finding_id}):
                    continue
                session.add(s.SemanticFindingLink(semantic_node_id=e.semantic_id, audit_finding_id=e.finding_id, strength=e.strength.value, evidence=e.evidence))

    def mark_findings_linked(self, finding_ids: list[int]) -> None:
        with self.Session() as session, session.begin():
            for fid in finding_ids:
                if not session.get(s.FindingLinkStatus, fid):
                    session.add(s.FindingLinkStatus(audit_finding_id=fid))


def _add_project_edge(session: Session, model, **pk):
    if session.get(model, pk) is None:
        session.add(model(**pk))


def _append(old: str, extra: str | None) -> str:
    extra = extra.strip() if extra else ""
    return old if not extra else (old.rstrip() + "\n\n" + extra if old else extra)


def _append_with_provenance(old: str, extra: str | None, *, kind: str, raw_name: str) -> str:
    extra = extra.strip() if extra else ""
    if not extra:
        return old
    return _append(old, f"— additional {kind} (from raw \"{raw_name}\"): {extra}")


def _get_or_create_completed_project(session: Session, project: ProjectData) -> s.Project:
    existing = None
    if project.platform_id:
        existing = session.scalar(
            select(s.Project)
            .join(s.ProjectPlatform, s.ProjectPlatform.project_id == s.Project.id)
            .where(s.ProjectPlatform.platform_id == project.platform_id)
        )
    if existing is None:
        existing = session.scalar(select(s.Project).where(s.Project.name == project.name))
    if existing is not None:
        existing.status = "completed"
        return existing

    proj = s.Project(name=project.name, status="completed")
    session.add(proj)
    session.flush()
    return proj


def write_project_completed(session: Session, project: ProjectData, categories: list, semantic_merge_results: list[SemanticMergeResult], finding_merge_results: list[FindingMergeResult], in_project_links: list[InProjectLink]) -> None:
    proj = _get_or_create_completed_project(session, project)
    if project.platform_id:
        existing_pp = session.scalar(select(s.ProjectPlatform).where(s.ProjectPlatform.project_id == proj.id))
        if existing_pp is None:
            session.add(s.ProjectPlatform(project_id=proj.id, platform_id=project.platform_id))
    seen_categories: set[str] = set()
    for cat0 in categories:
        cat = coerce_defi_category(cat0)
        if cat.value in seen_categories:
            continue
        seen_categories.add(cat.value)
        cat_row = session.scalar(select(s.Category).where(s.Category.name == cat.value))
        if cat_row:
            _add_project_edge(session, s.ProjectCategory, project_id=proj.id, category_id=cat_row.id)

    raw_semantic_ids: list[int] = []
    for res in semantic_merge_results:
        sem = res.semantic
        cat = coerce_defi_category(sem.category)
        node = s.SemanticNode(name=sem.name, definition=sem.definition, description=sem.description, category=cat.value)
        session.add(node); session.flush()
        raw_semantic_ids.append(node.id)
        for fn in sem.functions:
            session.add(s.SemanticFunction(semantic_node_id=node.id, function_name=fn.function_name, contract_path=fn.contract_path))
        _add_project_edge(session, s.ProjectSemantic, project_id=proj.id, semantic_node_id=node.id)
        if not res.decision.target_ids:
            if session.get(s.PendingSemantic, node.id) is None:
                session.add(s.PendingSemantic(semantic_node_id=node.id))
        else:
            for tid in res.decision.target_ids:
                if session.get(s.SemanticNode, tid) is None:
                    continue
                _add_project_edge(session, s.SemanticMerge, from_semantic_id=node.id, to_semantic_id=tid)
                _add_project_edge(session, s.ProjectSemantic, project_id=proj.id, semantic_node_id=tid)
                target = session.get(s.SemanticNode, tid)
                if target:
                    target.description = _append_with_provenance(target.description, res.decision.appended_description, kind="context", raw_name=sem.name)

    raw_finding_ids: list[int] = []
    for res in finding_merge_results:
        f = res.finding
        entry = resolve_taxonomy_entry(f.category, f.subcategory)
        if entry is None:
            raise ValueError(f"Invalid taxonomy pair: {f.category}/{f.subcategory}")
        finding = s.AuditFinding(title=f.title, severity=str(f.severity), root_cause=f.root_cause, description=f.description, patterns=f.patterns, exploits=f.exploits)
        session.add(finding); session.flush()
        raw_finding_ids.append(finding.id)
        fc = session.scalar(select(s.FindingCategory).where(s.FindingCategory.category == entry.category.value, s.FindingCategory.name == entry.subcategory))
        if fc:
            _add_project_edge(session, s.AuditFindingCategory, audit_finding_id=finding.id, finding_category_id=fc.id)
        _add_project_edge(session, s.ProjectFinding, project_id=proj.id, audit_finding_id=finding.id)
        if res.decision.target_ids:
            for tid in res.decision.target_ids:
                if session.get(s.AuditFinding, tid) is None:
                    continue
                _add_project_edge(session, s.FindingMerge, from_finding_id=finding.id, to_finding_id=tid)
                _add_project_edge(session, s.ProjectFinding, project_id=proj.id, audit_finding_id=tid)
                target = session.get(s.AuditFinding, tid)
                if target:
                    target.description = _append_with_provenance(target.description, res.decision.appended_description, kind="context", raw_name=f.title)
                    target.patterns = _append_with_provenance(target.patterns, res.decision.appended_patterns, kind="pattern", raw_name=f.title)
                    target.exploits = _append_with_provenance(target.exploits, res.decision.appended_exploits, kind="exploit", raw_name=f.title)

    for link in in_project_links:
        if 0 <= link.semantic_index < len(raw_semantic_ids) and 0 <= link.finding_index < len(raw_finding_ids):
            pk = {"semantic_node_id": raw_semantic_ids[link.semantic_index], "audit_finding_id": raw_finding_ids[link.finding_index]}
            if session.get(s.SemanticFindingLink, pk) is None:
                session.add(s.SemanticFindingLink(**pk, strength=link.strength.value, evidence=link.evidence))
