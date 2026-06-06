from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, field_validator

from .taxonomy import DeFiCategory, VulnerabilityCategory


class SourceFile(BaseModel):
    path: str
    content: str
    language: str | None = None


class AuditReportMaterial(BaseModel):
    content: str

    def render(self) -> str:
        return self.content


class ProjectData(BaseModel):
    name: str
    platform_id: str | None = None
    root_dir: Path
    source_language: Literal["solidity", "move", "mixed"] = "solidity"
    source_files: list[SourceFile] = Field(default_factory=list)
    audit_report: AuditReportMaterial | None = None


class SemanticFunction(BaseModel):
    contract_path: str
    function_name: str


class ExtractedSemantic(BaseModel):
    name: str
    category: DeFiCategory | str = DeFiCategory.Others
    definition: str
    description: str
    functions: list[SemanticFunction] = Field(default_factory=list)

    @field_validator("functions", mode="before")
    @classmethod
    def normalize_functions(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return value

        out = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, SemanticFunction):
                out.append(item)
            elif isinstance(item, str):
                out.append({"contract_path": "", "function_name": item})
            elif isinstance(item, dict):
                contract_path = (
                    item.get("contract_path")
                    or item.get("path")
                    or item.get("file")
                    or item.get("contract")
                    or ""
                )
                function_name = (
                    item.get("function_name")
                    or item.get("function")
                    or item.get("name")
                    or item.get("signature")
                    or item.get("description")
                    or ""
                )
                if function_name:
                    out.append({"contract_path": str(contract_path), "function_name": str(function_name)})
            else:
                out.append({"contract_path": "", "function_name": str(item)})
        return out


class FindingSeverity(str, Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"
    Informational = "Informational"


class ExtractedFinding(BaseModel):
    title: str
    severity: str = "Medium"
    category: VulnerabilityCategory | str
    subcategory: str
    root_cause: str
    description: str
    patterns: str = ""
    exploits: str = ""

    @field_validator("patterns", "exploits", mode="before")
    @classmethod
    def stringify_text_list(cls, value):
        return _stringify_text(value)


class LinkStrength(str, Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"


class InProjectLink(BaseModel):
    semantic_index: int
    finding_index: int
    strength: LinkStrength = LinkStrength.High
    evidence: str


class GlobalLink(BaseModel):
    semantic_id: int
    finding_id: int
    strength: LinkStrength = LinkStrength.Medium
    evidence: str


class SemanticMergeDecision(BaseModel):
    new_semantic_name: str
    target_ids: list[int] = Field(default_factory=list)
    appended_description: str | None = None
    reason: str = ""

    @field_validator("target_ids", mode="before")
    @classmethod
    def normalize_target_ids(cls, value):
        return _normalize_int_list(value)


class FindingMergeDecision(BaseModel):
    new_finding_title: str
    new_finding_index: int | None = None
    target_ids: list[int] = Field(default_factory=list)
    appended_description: str | None = None
    appended_patterns: str | None = None
    appended_exploits: str | None = None
    reason: str = ""

    @field_validator("target_ids", mode="before")
    @classmethod
    def normalize_target_ids(cls, value):
        return _normalize_int_list(value)

    @field_validator("appended_description", "appended_patterns", "appended_exploits", mode="before")
    @classmethod
    def normalize_optional_text(cls, value):
        text = _stringify_text(value)
        return text or None


class SemanticMergeResult(BaseModel):
    semantic: ExtractedSemantic
    decision: SemanticMergeDecision


class FindingMergeResult(BaseModel):
    finding: ExtractedFinding
    decision: FindingMergeDecision


class ProjectSpec(BaseModel):
    name: str
    path: Path
    platform_id: str | None = None

    @classmethod
    def parse(cls, spec: str) -> "ProjectSpec":
        parts = spec.split(":")
        if len(parts) < 2:
            raise ValueError("project spec must be name:path[:platform_id]")
        name = parts[0]
        platform_id = parts[-1] if len(parts) > 2 else None
        path = ":".join(parts[1:-1] if len(parts) > 2 else parts[1:])
        if not name or not path:
            raise ValueError("project spec must be name:path[:platform_id]")
        return cls(name=name, path=Path(path), platform_id=platform_id)


def _stringify_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(x) for x in value if x is not None)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def _normalize_int_list(value) -> list[int]:
    def dedupe(items: list[int]) -> list[int]:
        out = []
        seen = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    if value is None or value == "":
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        parts = [p for p in value.replace(",", " ").split() if p]
        out = []
        for part in parts:
            try:
                out.append(int(part))
            except ValueError:
                continue
        return dedupe(out)
    if isinstance(value, list):
        out = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return dedupe(out)
    return value
