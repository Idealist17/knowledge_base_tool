from __future__ import annotations
import asyncio
import time
from collections.abc import Callable
from .models import ProjectData
from .llm_client import LLMClient
from .db import HistoricalDatabase, write_project_completed
from .extract import categorize_project, extract_semantics, extract_findings
from .merge import merge_semantics, merge_findings
from .link import in_project_link, global_link
from .config import LLMConfig


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)


async def learn_project(db: HistoricalDatabase, llm: LLMClient, project: ProjectData, *, config: LLMConfig | None = None, run_global_link: bool = False, logger: Callable[[str], None] | None = None) -> None:
    config = config or LLMConfig()
    key = project.platform_id or project.name
    if db.is_project_completed(key):
        _log(logger, f"[yellow]skip[/yellow] project={project.name} key={key} status=completed")
        return
    started = time.monotonic()
    _log(logger, f"[bold cyan]project start[/bold cyan] name={project.name} key={key} files={len(project.source_files)} report={'yes' if project.audit_report else 'no'}")
    _log(logger, "  [cyan]stage[/cyan] categorize")
    categories = await categorize_project(llm, project)
    _log(logger, "  [green]done[/green] categorize categories=" + ",".join(c.value if hasattr(c, "value") else str(c) for c in categories))
    _log(logger, f"  [cyan]stage[/cyan] extract semantics/findings budgets=({config.input_token_budget},{config.finding_token_budget})")
    sem_task = extract_semantics(llm, project, categories, config.input_token_budget, config.model)
    find_task = extract_findings(llm, project, categories, config.finding_token_budget, config.model)
    semantics, findings = await asyncio.gather(sem_task, find_task)
    fn_count = sum(len(s.functions) for s in semantics)
    _log(logger, f"  [green]done[/green] extract semantics={len(semantics)} functions={fn_count} findings={len(findings)}")
    _log(logger, "  [cyan]stage[/cyan] in-project link")
    links = await in_project_link(llm, semantics, findings)
    _log(logger, f"  [green]done[/green] in-project link links={len(links)}")
    canon_sem = db.canonical_semantics_with_children_for_categories([c.value for c in categories])
    _log(logger, f"  [cyan]stage[/cyan] merge semantics new={len(semantics)} canon_candidates={len(canon_sem)}")
    sem_results = await merge_semantics(llm, semantics, canon_sem)
    canon_find = db.canonical_findings_with_children_for_categories([c.value for c in categories])
    sem_merge_count = sum(1 for r in sem_results if r.decision.target_ids)
    _log(logger, f"  [green]done[/green] merge semantics merged={sem_merge_count} new={len(sem_results) - sem_merge_count}")
    _log(logger, f"  [cyan]stage[/cyan] merge findings new={len(findings)} canon_candidates={len(canon_find)}")
    find_results = await merge_findings(llm, findings, canon_find)
    find_merge_count = sum(1 for r in find_results if r.decision.target_ids)
    _log(logger, f"  [green]done[/green] merge findings merged={find_merge_count} new={len(find_results) - find_merge_count}")
    _log(logger, "  [cyan]stage[/cyan] write database")
    with db.Session() as session, session.begin():
        write_project_completed(session, project, categories, sem_results, find_results, links)
    _log(logger, f"  [green]done[/green] write project={project.name}")
    if run_global_link:
        _log(logger, "  [cyan]stage[/cyan] global link")
        edges = await global_link(llm, db, logger=logger)
        _log(logger, f"  [green]done[/green] global link edges={len(edges)}")
    _log(logger, f"[bold green]project done[/bold green] name={project.name} elapsed={time.monotonic() - started:.1f}s")


async def learn_projects(db: HistoricalDatabase, llm: LLMClient, projects: list[ProjectData], *, concurrency: int = 1, run_global_link: bool = False, config: LLMConfig | None = None, logger: Callable[[str], None] | None = None) -> None:
    # Keep merge/write serial so each project sees the canonical KG produced by prior projects.
    # Inside learn_project, semantic and finding extraction still run concurrently.
    started = time.monotonic()
    _log(logger, f"[bold]learn start[/bold] projects={len(projects)} concurrency={concurrency} global_link={run_global_link}")
    for project in projects:
        await learn_project(db, llm, project, config=config, run_global_link=False, logger=logger)
    if run_global_link:
        _log(logger, "[cyan]stage[/cyan] final global link")
        edges = await global_link(llm, db, logger=logger)
        _log(logger, f"[green]done[/green] final global link edges={len(edges)}")
    _log(logger, f"[bold green]learn done[/bold green] projects={len(projects)} elapsed={time.monotonic() - started:.1f}s")
