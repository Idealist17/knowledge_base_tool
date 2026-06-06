from __future__ import annotations
from .llm_client import LLMClient
from .models import ProjectData, ExtractedSemantic, ExtractedFinding
from .taxonomy import coerce_defi_category, resolve_taxonomy_entry
from .token_utils import chunk_text
from .normalize import ensure_list
from . import prompts


def dedup_semantics(items: list[ExtractedSemantic]) -> list[ExtractedSemantic]:
    by_name: dict[str, ExtractedSemantic] = {}
    for sem in items:
        sem.name = sem.name.strip()
        sem.definition = sem.definition.strip()
        sem.description = sem.description.strip()
        key = sem.name.lower().strip()
        if not key:
            continue
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = sem
            continue
        seen_funcs = {(f.contract_path, f.function_name) for f in existing.functions}
        for fn in sem.functions:
            fn_key = (fn.contract_path, fn.function_name)
            if fn_key not in seen_funcs:
                existing.functions.append(fn)
                seen_funcs.add(fn_key)
        if len(sem.description) > len(existing.description):
            existing.description = sem.description
            existing.definition = sem.definition
    return list(by_name.values())


def dedup_findings(items: list[ExtractedFinding]) -> list[ExtractedFinding]:
    severity_rank = {"Informational": 0, "Low": 1, "Medium": 2, "High": 3}
    by_title: dict[str, ExtractedFinding] = {}
    for finding in items:
        finding.title = finding.title.strip()
        finding.root_cause = finding.root_cause.strip()
        finding.description = finding.description.strip()
        finding.patterns = finding.patterns.strip()
        finding.exploits = finding.exploits.strip()
        key = finding.title.lower().strip()
        if not key:
            continue
        existing = by_title.get(key)
        if existing is None:
            by_title[key] = finding
            continue
        if severity_rank.get(str(finding.severity), 0) > severity_rank.get(str(existing.severity), 0):
            existing.severity = finding.severity
        if len(finding.description) > len(existing.description):
            existing.category = finding.category
            existing.subcategory = finding.subcategory
            existing.description = finding.description
        if len(finding.root_cause) > len(existing.root_cause):
            existing.root_cause = finding.root_cause
        if len(finding.patterns) > len(existing.patterns):
            existing.patterns = finding.patterns
        if len(finding.exploits) > len(existing.exploits):
            existing.exploits = finding.exploits
    return list(by_title.values())


async def categorize_project(llm: LLMClient, project: ProjectData) -> list:
    raw = await llm.json(prompts.categorize_prompt(project), schema_name="categorize")
    raw = ensure_list(raw, "items", "categories")
    cats = []
    for x in raw:
        if isinstance(x, dict):
            x = x.get("category", x.get("name", x.get("value", "")))
        cats.append(coerce_defi_category(x))
    deduped = []
    seen = set()
    for cat in cats:
        if cat.value in seen:
            continue
        seen.add(cat.value)
        deduped.append(cat)
    return deduped or [coerce_defi_category("Others")]


class SemanticAgentBuffer:
    def __init__(self, allowed_categories: set[str]) -> None:
        self.allowed_categories = allowed_categories | {"Others"}
        self.items: list[ExtractedSemantic] = []
        self.finished = False
        self.errors: list[str] = []

    def report_semantic(self, args: dict) -> str:
        if self.finished:
            msg = "error: extraction is already finished; do not report more semantics"
            self.errors.append(msg)
            return msg
        try:
            semantic = ExtractedSemantic.model_validate(args)
        except Exception as exc:
            msg = f"error: invalid semantic payload: {exc}"
            self.errors.append(msg)
            return msg
        if not semantic.name.strip():
            msg = "error: `name` must not be empty"
            self.errors.append(msg)
            return msg
        if str(semantic.category) not in self.allowed_categories:
            msg = f"error: `category` must be one of {sorted(self.allowed_categories)}"
            self.errors.append(msg)
            return msg
        if not semantic.functions:
            msg = "error: `functions` must contain at least one source function"
            self.errors.append(msg)
            return msg
        for fn in semantic.functions:
            if not fn.contract_path.strip() or not fn.function_name.strip():
                msg = "error: every function must include non-empty contract_path and function_name"
                self.errors.append(msg)
                return msg
        self.items.append(semantic)
        return "ok: semantic recorded"

    def finish(self, args: dict) -> str:
        if self.errors:
            return "error: cannot finish while previous report_semantic calls are invalid; restart or retry this chunk"
        self.finished = True
        summary = args.get("summary") if isinstance(args, dict) else None
        return f"ok: finished{f' - {summary}' if summary else ''}"


async def extract_semantics(llm: LLMClient, project: ProjectData, categories: list, token_budget: int = 24000, model: str = "gpt-5.4-mini") -> list[ExtractedSemantic]:
    text = prompts.render_sources(project)
    out: list[ExtractedSemantic] = []
    category_values = [c.value if hasattr(c, 'value') else str(c) for c in categories]
    for chunk in chunk_text(text, token_budget, model):
        buffer = SemanticAgentBuffer(set(category_values))
        try:
            await llm.agent(
                system_prompt=prompts.semantic_extract_system_prompt(),
                user_prompt=prompts.semantic_extract_prompt(project, chunk, category_values),
                tools=prompts.semantic_tools_schema(),
                tool_handlers={
                    "report_semantic": buffer.report_semantic,
                    "finish": buffer.finish,
                },
                schema_name="semantic_extract",
                stop_condition=lambda: buffer.finished,
            )
        except RuntimeError as exc:
            if buffer.errors:
                raise RuntimeError("semantic extraction agent reported invalid semantics: " + "; ".join(buffer.errors)) from exc
            raise
        if buffer.errors:
            raise RuntimeError("semantic extraction agent reported invalid semantics: " + "; ".join(buffer.errors))
        if not buffer.finished:
            raise RuntimeError("semantic extraction agent stopped before calling finish")
        out.extend(buffer.items)
    return dedup_semantics(out)


async def extract_findings(llm: LLMClient, project: ProjectData, categories: list, token_budget: int = 16000, model: str = "gpt-5.4-mini") -> list[ExtractedFinding]:
    if not project.audit_report:
        return []
    out: list[ExtractedFinding] = []
    for chunk in chunk_text(project.audit_report.render(), token_budget, model):
        raw = await llm.json(prompts.finding_extract_prompt(project, chunk, [c.value if hasattr(c,'value') else str(c) for c in categories]), schema_name="finding_extract")
        raw = ensure_list(raw, "items", "findings")
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            f = ExtractedFinding.model_validate(item)
            entry = resolve_taxonomy_entry(f.category, f.subcategory)
            if entry is None:
                raise ValueError(f"Invalid taxonomy pair from LLM: {f.category}/{f.subcategory}")
            f.category = entry.category; f.subcategory = entry.subcategory
            out.append(f)
    return dedup_findings(out)
