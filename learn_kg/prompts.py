from __future__ import annotations
import json
from .models import ProjectData, ExtractedSemantic, ExtractedFinding
from .taxonomy import taxonomy_prompt, all_defi_categories


def render_sources(project: ProjectData, max_chars: int | None = None) -> str:
    out = []
    for f in project.source_files:
        out.append(f"## File: {f.path}\n```\n{f.content}\n```")
    text = "\n\n".join(out)
    return text[:max_chars] if max_chars else text


def categorize_prompt(project: ProjectData) -> str:
    cats = ", ".join(c.value for c in all_defi_categories())
    return (
        "Classify this smart contract project into DeFi categories. "
        "Return exactly one JSON object: {\"items\":[\"Category\"]}. "
        f"Every category must be one of: {cats}.\n\n"
        f"{render_sources(project, 30000)}"
    )


def semantic_extract_prompt(project: ProjectData, chunk: str, categories: list[str]) -> str:
    return (
        "Extract project-agnostic DeFi semantics from the source chunk. "
        "Do not include protocol/contract/brand names in name/definition/description. "
        "Return exactly one JSON object with this shape: "
        "{\"items\":[{\"name\":\"...\",\"category\":\"...\",\"definition\":\"...\",\"description\":\"...\","
        "\"functions\":[{\"contract_path\":\"path/to/Contract.sol\",\"function_name\":\"functionName\"}]}]}. "
        "The functions array must contain objects only, never strings. "
        f"Known categories: {categories}\n\n{chunk}"
    )


def finding_extract_prompt(project: ProjectData, chunk: str, categories: list[str]) -> str:
    return (
        "Extract audit findings by independent root cause. "
        "Return exactly one JSON object with this shape: "
        "{\"items\":[{\"title\":\"...\",\"severity\":\"High|Medium|Low|Informational\","
        "\"category\":\"...\",\"subcategory\":\"...\",\"root_cause\":\"...\",\"description\":\"...\","
        "\"patterns\":\"single string\",\"exploits\":\"single string\"}]}. "
        "patterns and exploits must be strings, not arrays. "
        "category/subcategory must be from the vulnerability taxonomy below. "
        "Do not put the DeFi project category in finding.category; project categories are context only. "
        f"Project categories for context only: {categories}\n\n{taxonomy_prompt()}\n\nREPORT:\n{chunk}"
    )


def in_project_link_prompt(semantics: list[ExtractedSemantic], findings: list[ExtractedFinding]) -> str:
    return "Link every finding to at least one semantic by zero-based indexes. Return exactly one JSON object: {\"items\":[{\"semantic_index\":0,\"finding_index\":0,\"strength\":\"High|Medium|Low\",\"evidence\":\"...\"}]}\nSEMANTICS:\n" + json.dumps([x.model_dump(mode='json') for x in semantics], indent=2) + "\nFINDINGS:\n" + json.dumps([x.model_dump(mode='json') for x in findings], indent=2)


def semantic_merge_prompt(new_semantics: list[ExtractedSemantic], canonicals: list[dict]) -> str:
    return "Decide whether each new semantic is NEW or merges to target canonical ids. Support multiple targets. Return exactly one JSON object: {\"items\":[{\"new_semantic_name\":\"...\",\"target_ids\":[1],\"appended_description\":\"...\",\"reason\":\"...\"}]}\nNEW:\n" + json.dumps([x.model_dump(mode='json') for x in new_semantics], indent=2) + "\nCANONICALS:\n" + json.dumps(canonicals, indent=2)


def finding_merge_prompt(new_findings: list[ExtractedFinding], canonicals: list[dict]) -> str:
    return "Decide whether each new finding is NEW or merges to target canonical ids. Support multiple targets. Return exactly one JSON object: {\"items\":[{\"new_finding_title\":\"...\",\"target_ids\":[1],\"appended_description\":\"...\",\"appended_patterns\":\"...\",\"appended_exploits\":\"...\",\"reason\":\"...\"}]}\nNEW:\n" + json.dumps([x.model_dump(mode='json') for x in new_findings], indent=2) + "\nCANONICALS:\n" + json.dumps(canonicals, indent=2)


def global_link_prompt(findings: list[dict], semantics: list[dict]) -> str:
    return "Link canonical findings to canonical semantics. Omit unrelated pairs. Return exactly one JSON object: {\"items\":[{\"semantic_id\":1,\"finding_id\":1,\"strength\":\"High|Medium|Low\",\"evidence\":\"...\"}]}\nFINDINGS:\n" + json.dumps(findings, indent=2) + "\nSEMANTICS:\n" + json.dumps(semantics, indent=2)
