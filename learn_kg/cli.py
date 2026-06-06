from __future__ import annotations
import asyncio
from pathlib import Path
import typer
from rich.console import Console
from dotenv import load_dotenv

from .db import HistoricalDatabase, init_db, describe_db_url
from .project_loader import load_project, parse_reports
from .c4_loader import select_contest_ids, load_c4_project
from .models import ProjectSpec
from .llm_client import OpenAILLMClient
from .config import LLMConfig
from .pipeline import learn_projects as run_learn_projects
from .link import global_link as run_global_link
from .export import export_dot as do_export_dot, export_html as do_export_html, export_counts

load_dotenv()
app = typer.Typer(help="Build and explore a local smart-contract audit knowledge graph")
console = Console()


def make_logger(verbose: bool):
    return console.print if verbose else None


def make_llm(config: LLMConfig, *, verbose: bool = False) -> OpenAILLMClient:
    return OpenAILLMClient(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        logger=make_logger(verbose),
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )


@app.command("init-db")
def init_db_cmd(db: str = typer.Option(..., "--db")):
    init_db(db)
    console.print(f"[green]initialized[/green] {describe_db_url(db)}")


@app.command("learn-projects")
def learn_projects_cmd(
    db: str = typer.Option(..., "--db"),
    project: list[str] = typer.Option([], "--project"),
    report: list[str] = typer.Option([], "--report"),
    link: bool = typer.Option(False, "--link"),
    concurrency: int = typer.Option(1, "--concurrency"),
    input_token_budget: int = typer.Option(24000, "--input-token-budget"),
    finding_token_budget: int = typer.Option(16000, "--finding-token-budget"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", help="Show detailed terminal progress logs."),
):
    kg = HistoricalDatabase(db); kg.init()
    reports = parse_reports(report)
    projects = [load_project(ProjectSpec.parse(p), reports.get(ProjectSpec.parse(p).name)) for p in project]
    cfg = LLMConfig(input_token_budget=input_token_budget, finding_token_budget=finding_token_budget)
    log = make_logger(verbose)
    if log:
        log(f"[bold]config[/bold] db={describe_db_url(db)} model={cfg.model} base_url={cfg.base_url or 'default'} retries={cfg.max_retries} timeout={cfg.request_timeout}s projects={len(projects)}")
    asyncio.run(run_learn_projects(kg, make_llm(cfg, verbose=verbose), projects, concurrency=concurrency, run_global_link=link, config=cfg, logger=log))


@app.command("learn-c4")
def learn_c4_cmd(
    db: str = typer.Option(..., "--db"),
    c4_dir: Path = typer.Option(..., "--c4-dir"),
    c4_ids: str | None = typer.Option(None, "--c4-ids"),
    skip_ids: str | None = typer.Option(None, "--skip-ids"),
    limit: int | None = typer.Option(None, "--limit"),
    concurrency: int = typer.Option(1, "--concurrency"),
    link: bool = typer.Option(False, "--link"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", help="Show detailed terminal progress logs."),
):
    kg = HistoricalDatabase(db); kg.init()
    ids = select_contest_ids(c4_dir, c4_ids, skip_ids, limit)
    log = make_logger(verbose)
    if log:
        log(f"[bold]config[/bold] db={describe_db_url(db)} c4_dir={c4_dir} ids={','.join(map(str, ids)) or '(none)'} link={link}")
    projects = []
    skipped = []
    for cid in ids:
        key = f"c4-{cid}"
        if kg.is_project_completed(key):
            skipped.append(cid)
            continue
        projects.append(load_c4_project(c4_dir, cid))
    cfg = LLMConfig()
    if log:
        log(f"[bold]selected[/bold] total_ids={len(ids)} to_process={len(projects)} skipped_completed={skipped or []} model={cfg.model} base_url={cfg.base_url or 'default'} retries={cfg.max_retries} timeout={cfg.request_timeout}s")
    asyncio.run(run_learn_projects(kg, make_llm(cfg, verbose=verbose), projects, concurrency=concurrency, run_global_link=link, config=cfg, logger=log))
    if log:
        log(f"[bold]db counts[/bold] {kg.counts()}")


@app.command("link")
def link_cmd(db: str = typer.Option(..., "--db"), concurrency: int = typer.Option(1, "--concurrency"), verbose: bool = typer.Option(True, "--verbose/--quiet", help="Show detailed terminal progress logs.")):
    kg = HistoricalDatabase(db); cfg = LLMConfig()
    log = make_logger(verbose)
    if log:
        log(f"[bold]config[/bold] db={describe_db_url(db)} model={cfg.model} base_url={cfg.base_url or 'default'} retries={cfg.max_retries} timeout={cfg.request_timeout}s")
    edges = asyncio.run(run_global_link(make_llm(cfg, verbose=verbose), kg, logger=log))
    console.print(f"linked {len(edges)} edges")


@app.command("list-projects")
def list_projects_cmd(db: str = typer.Option(..., "--db")):
    kg = HistoricalDatabase(db)
    rows = kg.list_projects()
    if not rows:
        console.print(f"[yellow]no projects found[/yellow] db={describe_db_url(db)} counts={kg.counts()}")
        return
    console.print(f"[dim]db={describe_db_url(db)}[/dim]")
    for pid, name, platform, status in rows:
        console.print(f"{pid}\t{name}\t{platform or ''}\t{status}")


@app.command("list-semantics")
def list_semantics_cmd(db: str = typer.Option(..., "--db"), project: str | None = typer.Option(None, "--project")):
    for n in HistoricalDatabase(db).list_semantics(project):
        console.print(f"{n.id}\t{n.category}\t{n.name}")


@app.command("search-semantics")
def search_semantics_cmd(db: str = typer.Option(..., "--db"), keyword: str = typer.Option(..., "--keyword")):
    for n in HistoricalDatabase(db).search_semantics(keyword):
        console.print(f"{n.id}\t{n.category}\t{n.name}")


@app.command("export-dot")
def export_dot_cmd(db: str = typer.Option(..., "--db"), out: Path = typer.Option(..., "--out")):
    kg = HistoricalDatabase(db)
    counts = export_counts(kg)
    do_export_dot(kg, out)
    console.print(f"{out} counts={counts} db={describe_db_url(db)}")
    if counts["projects"] == 0:
        console.print("[yellow]warning[/yellow] exported an empty graph; check that --db points to the sqlite file used by learn-c4")


@app.command("export-html")
def export_html_cmd(db: str = typer.Option(..., "--db"), out: Path = typer.Option(..., "--out")):
    kg = HistoricalDatabase(db)
    counts = export_counts(kg)
    do_export_html(kg, out)
    console.print(f"{out} counts={counts} db={describe_db_url(db)}")
    if counts["projects"] == 0:
        console.print("[yellow]warning[/yellow] exported an empty graph; check that --db points to the sqlite file used by learn-c4")


if __name__ == "__main__":
    app()
