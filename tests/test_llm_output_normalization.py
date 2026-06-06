import pytest

from learn_kg.models import ExtractedSemantic, ExtractedFinding, SemanticMergeDecision, FindingMergeDecision
from learn_kg.normalize import ensure_list
from learn_kg.link import in_project_link
from learn_kg.llm_client import MockLLMClient


def test_semantic_functions_accept_llm_string_items():
    sem = ExtractedSemantic.model_validate({
        "name": "Off-chain Order Lifecycle",
        "category": "Dexes",
        "definition": "orders are signed off-chain and settled on-chain",
        "description": "signature validation and settlement flow",
        "functions": [
            "create signed off-chain order",
            {"file": "src/Exchange.sol", "function": "fillOrder"},
        ],
    })
    assert sem.functions[0].contract_path == ""
    assert sem.functions[0].function_name == "create signed off-chain order"
    assert sem.functions[1].contract_path == "src/Exchange.sol"
    assert sem.functions[1].function_name == "fillOrder"


def test_finding_stringifies_list_fields():
    finding = ExtractedFinding.model_validate({
        "title": "Fee bypass",
        "severity": "Medium",
        "category": "Access Control",
        "subcategory": "Missing Input Validation",
        "root_cause": "unchecked exercise amount",
        "description": "desc",
        "patterns": ["withdraw fee path", "exercise amount path"],
        "exploits": ["pay less fee"],
    })
    assert finding.patterns == "withdraw fee path\nexercise amount path"
    assert finding.exploits == "pay less fee"


def test_merge_decisions_normalize_target_ids_and_text():
    sem = SemanticMergeDecision.model_validate({"new_semantic_name": "S", "target_ids": "1, 2 x"})
    finding = FindingMergeDecision.model_validate({
        "new_finding_title": "F",
        "target_ids": 3,
        "appended_patterns": ["a", "b"],
    })
    assert sem.target_ids == [1, 2]
    assert finding.target_ids == [3]
    assert finding.appended_patterns == "a\nb"


def test_ensure_list_handles_json_mode_object_variants():
    assert ensure_list({"items": [1]}) == [1]
    assert ensure_list({"semantics": [{"name": "x"}]}, "items", "semantics") == [{"name": "x"}]
    assert ensure_list({"name": "single"}) == [{"name": "single"}]


@pytest.mark.asyncio
async def test_in_project_link_drops_invalid_indexes_and_adds_default():
    sem = ExtractedSemantic(name="S", category="Lending", definition="d", description="d")
    finding = ExtractedFinding(title="F", severity="High", category="Reentrancy", subcategory="Reentrancy Vulnerability with ETH Transfer", root_cause="r", description="d")
    links = await in_project_link(MockLLMClient([[{"semantic_index": 99, "finding_index": 0, "evidence": "bad"}]]), [sem], [finding])
    assert len(links) == 1
    assert links[0].semantic_index == 0
    assert links[0].finding_index == 0

from learn_kg.taxonomy import resolve_taxonomy_entry, VulnerabilityCategory


def test_taxonomy_recovers_when_llm_uses_defi_category_for_finding_category():
    entry = resolve_taxonomy_entry("Derivatives", "Lack of Proper Signature Verification")
    assert entry is not None
    assert entry.category == VulnerabilityCategory.Cryptographic

from sqlalchemy import select, func
from learn_kg.extract import categorize_project
from learn_kg.merge import merge_semantics, merge_findings
from learn_kg.db import HistoricalDatabase
from learn_kg import schema as s
from learn_kg.models import ProjectData
from learn_kg.link import global_link
from pathlib import Path


def test_ensure_list_wraps_dict_valued_items():
    assert ensure_list({"items": {"name": "x"}}, "items") == [{"name": "x"}]
    assert ensure_list({"links": {"semantic_id": 1}}, "items", "links") == [{"semantic_id": 1}]


@pytest.mark.asyncio
async def test_categorize_project_accepts_object_categories(tmp_path):
    project = ProjectData(name="p", root_dir=tmp_path, source_files=[])
    cats = await categorize_project(MockLLMClient([{"items": [{"category": "Dexes"}, {"name": "Lending"}]}]), project)
    assert [c.value for c in cats] == ["Dexes", "Lending"]


@pytest.mark.asyncio
async def test_merge_matches_names_with_extra_whitespace():
    sem = ExtractedSemantic(name="Reentrant Exit", category="Lending", definition="d", description="d")
    finding = ExtractedFinding(title="Fee Bypass", severity="Medium", category="Access Control", subcategory="Missing Input Validation", root_cause="r", description="d")
    sem_results = await merge_semantics(
        MockLLMClient([[{"new_semantic_name": "  reentrant   exit  ", "target_ids": [7]}]]),
        [sem],
        [{"id": 7, "name": "canonical"}],
    )
    finding_results = await merge_findings(
        MockLLMClient([[{"new_finding_title": " fee   bypass ", "target_ids": "8"}]]),
        [finding],
        [{"id": 8, "title": "canonical"}],
    )
    assert sem_results[0].decision.target_ids == [7]
    assert finding_results[0].decision.target_ids == [8]


@pytest.mark.asyncio
async def test_global_link_does_not_mark_when_all_edges_invalid(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    with db.Session() as session, session.begin():
        sem = s.SemanticNode(name="S", definition="d", description="d", category="Lending")
        finding = s.AuditFinding(title="F", severity="High", root_cause="r", description="d", patterns="", exploits="")
        session.add_all([sem, finding])
    edges = await global_link(MockLLMClient([[{"semantic_id": 999, "finding_id": 999, "evidence": "bad"}]]), db)
    assert edges == []
    with db.Session() as session:
        assert session.scalar(select(s.FindingLinkStatus.audit_finding_id)) is None

from learn_kg.db import write_project_completed
from learn_kg.models import SemanticMergeResult, FindingMergeResult, SemanticMergeDecision, FindingMergeDecision, InProjectLink


@pytest.mark.asyncio
async def test_categorize_project_dedupes_categories(tmp_path):
    project = ProjectData(name="p", root_dir=tmp_path, source_files=[])
    cats = await categorize_project(MockLLMClient([{"items": ["Cross Chain", {"category": "Cross Chain"}, {"name": "Lending"}]}]), project)
    assert [c.value for c in cats] == ["Cross Chain", "Lending"]


def test_write_project_completed_dedupes_project_categories(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    project = ProjectData(name="p", platform_id="p", root_dir=tmp_path, source_files=[])
    sem = ExtractedSemantic(name="S", category="Lending", definition="d", description="d")
    finding = ExtractedFinding(title="F", severity="Medium", category="Access Control", subcategory="Missing Input Validation", root_cause="r", description="d")
    with db.Session() as session, session.begin():
        write_project_completed(
            session,
            project,
            ["Cross Chain", "Cross Chain", "Lending"],
            [SemanticMergeResult(semantic=sem, decision=SemanticMergeDecision(new_semantic_name="S"))],
            [FindingMergeResult(finding=finding, decision=FindingMergeDecision(new_finding_title="F"))],
            [InProjectLink(semantic_index=0, finding_index=0, evidence="e")],
        )
    with db.Session() as session:
        assert session.scalar(select(func.count()).select_from(s.ProjectCategory)) == 2


def test_merge_decision_target_ids_are_deduped():
    dec = SemanticMergeDecision.model_validate({"new_semantic_name": "S", "target_ids": [1, "1", 2]})
    assert dec.target_ids == [1, 2]

from learn_kg.extract import dedup_semantics, dedup_findings
from learn_kg.models import SemanticFunction


def test_dedup_semantics_merges_duplicate_names():
    a = ExtractedSemantic(name=" Flow ", category="Lending", definition="short", description="short", functions=[SemanticFunction(contract_path="A.sol", function_name="f")])
    b = ExtractedSemantic(name="flow", category="Lending", definition="long definition", description="longer description", functions=[SemanticFunction(contract_path="B.sol", function_name="g")])
    out = dedup_semantics([a, b])
    assert len(out) == 1
    assert out[0].name == "Flow"
    assert out[0].definition == "long definition"
    assert len(out[0].functions) == 2


def test_dedup_findings_merges_duplicate_titles():
    a = ExtractedFinding(title=" Bug ", severity="Low", category="Access Control", subcategory="Missing Input Validation", root_cause="r", description="d", patterns="p", exploits="e")
    b = ExtractedFinding(title="bug", severity="High", category="Cryptographic", subcategory="Lack of Proper Signature Verification", root_cause="long root", description="longer description", patterns="long pattern", exploits="long exploit")
    out = dedup_findings([a, b])
    assert len(out) == 1
    assert out[0].title == "Bug"
    assert out[0].severity == "High"
    assert out[0].root_cause == "long root"
    assert out[0].subcategory == "Lack of Proper Signature Verification"


def test_write_project_completed_upserts_existing_project_and_edges(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    project = ProjectData(name="p", platform_id="p", root_dir=tmp_path, source_files=[])
    sem = ExtractedSemantic(name="S", category="Lending", definition="d", description="d")
    finding = ExtractedFinding(title="F", severity="Medium", category="Access Control", subcategory="Missing Input Validation", root_cause="r", description="d")
    with db.Session() as session, session.begin():
        write_project_completed(session, project, ["Lending"], [SemanticMergeResult(semantic=sem, decision=SemanticMergeDecision(new_semantic_name="S"))], [FindingMergeResult(finding=finding, decision=FindingMergeDecision(new_finding_title="F"))], [])
    with db.Session() as session, session.begin():
        write_project_completed(session, project, ["Lending", "Lending"], [], [], [])
    with db.Session() as session:
        assert session.scalar(select(func.count()).select_from(s.Project)) == 1
        assert session.scalar(select(func.count()).select_from(s.ProjectPlatform)) == 1
        assert session.scalar(select(func.count()).select_from(s.ProjectCategory)) == 1
