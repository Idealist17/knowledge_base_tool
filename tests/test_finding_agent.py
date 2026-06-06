import pytest

from learn_kg.extract import extract_findings, dedup_findings
from learn_kg.llm_client import MockLLMClient
from learn_kg.models import AuditReportMaterial, ExtractedFinding, ProjectData
from learn_kg.prompts import finding_tools_schema
from learn_kg.taxonomy import VulnerabilityCategory


def project_with_report(tmp_path, report="## H-1 Reentrant withdraw\nExternal call before state update."):
    return ProjectData(name="p", root_dir=tmp_path, source_files=[], audit_report=AuditReportMaterial(content=report))


def finding_args(**overrides):
    data = {
        "title": "Reentrant withdraw",
        "severity": "High",
        "category": "Reentrancy",
        "subcategory": "Reentrancy Vulnerability with ETH Transfer",
        "root_cause": "external call before balance update",
        "description": "A user balance remains unchanged while an outbound native asset transfer hands control to the receiver.",
        "patterns": "external value transfer occurs before the balance slot is decremented",
        "exploits": "attacker deposits, calls withdrawal, reenters before balance is decremented, and repeats withdrawal",
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_extract_findings_uses_report_finding_and_finish(tmp_path):
    llm = MockLLMClient([[
        {"tool": "report_finding", "args": finding_args()},
        {"tool": "finish", "args": {"summary": "one finding"}},
    ]])

    out = await extract_findings(llm, project_with_report(tmp_path), ["Lending"])

    assert len(out) == 1
    assert out[0].title == "Reentrant withdraw"
    assert out[0].category == VulnerabilityCategory.Reentrancy
    prompt = llm.prompts[0]
    assert "report_finding" in prompt
    assert "finish" in prompt
    assert "Atomic decomposition" in prompt
    assert "do not include protocol names" in prompt


@pytest.mark.asyncio
async def test_extract_findings_allows_empty_report_chunk(tmp_path):
    out = await extract_findings(
        MockLLMClient([[{"tool": "finish", "args": {"summary": "no findings"}}]]),
        project_with_report(tmp_path, "No issues."),
        ["Others"],
    )
    assert out == []


@pytest.mark.asyncio
async def test_extract_findings_rejects_missing_finish(tmp_path):
    with pytest.raises(RuntimeError, match="without finish|before calling finish"):
        await extract_findings(
            MockLLMClient([[{"tool": "report_finding", "args": finding_args()}]]),
            project_with_report(tmp_path),
            ["Lending"],
        )


@pytest.mark.asyncio
async def test_extract_findings_rejects_invalid_taxonomy_even_if_finish_follows(tmp_path):
    with pytest.raises(RuntimeError, match="invalid taxonomy"):
        await extract_findings(
            MockLLMClient([[
                {"tool": "report_finding", "args": finding_args(category="Lending", subcategory="Not Real")},
                {"tool": "finish", "args": {}},
            ]]),
            project_with_report(tmp_path),
            ["Lending"],
        )


@pytest.mark.asyncio
async def test_extract_findings_rejects_informational_severity(tmp_path):
    with pytest.raises(RuntimeError, match="severity"):
        await extract_findings(
            MockLLMClient([[
                {"tool": "report_finding", "args": finding_args(severity="Informational")},
                {"tool": "finish", "args": {}},
            ]]),
            project_with_report(tmp_path),
            ["Lending"],
        )


@pytest.mark.asyncio
async def test_extract_findings_rejects_empty_patterns_or_exploits(tmp_path):
    with pytest.raises(RuntimeError, match="patterns"):
        await extract_findings(
            MockLLMClient([[
                {"tool": "report_finding", "args": finding_args(patterns="")},
                {"tool": "finish", "args": {}},
            ]]),
            project_with_report(tmp_path),
            ["Lending"],
        )


@pytest.mark.asyncio
async def test_extract_findings_rejects_report_after_finish(tmp_path):
    with pytest.raises(RuntimeError, match="already finished|invalid findings"):
        await extract_findings(
            MockLLMClient([[
                {"tool": "finish", "args": {}},
                {"tool": "report_finding", "args": finding_args()},
            ]]),
            project_with_report(tmp_path),
            ["Lending"],
        )


def test_finding_tool_schema_requires_python_field_names():
    report_tool = next(t for t in finding_tools_schema() if t["function"]["name"] == "report_finding")
    params = report_tool["function"]["parameters"]
    assert params["required"] == [
        "title",
        "severity",
        "category",
        "subcategory",
        "root_cause",
        "description",
        "patterns",
        "exploits",
    ]
    assert params["properties"]["severity"]["enum"] == ["High", "Medium", "Low"]


def test_dedup_findings_keeps_same_title_different_root_causes():
    a = ExtractedFinding(**finding_args(root_cause="external call before balance update"))
    b = ExtractedFinding(**finding_args(root_cause="missing caller authorization", category="Access Control", subcategory="Missing Input Validation"))
    out = dedup_findings([a, b])
    assert len(out) == 2
    assert {f.root_cause for f in out} == {"external call before balance update", "missing caller authorization"}


def test_dedup_findings_merges_same_title_same_root_cause_normalized():
    a = ExtractedFinding(**finding_args(severity="Low", root_cause=" external   call before balance update ", description="short"))
    b = ExtractedFinding(**finding_args(severity="High", root_cause="External call before balance update", description="much longer concrete description"))
    out = dedup_findings([a, b])
    assert len(out) == 1
    assert out[0].severity == "High"
    assert out[0].description == "much longer concrete description"

@pytest.mark.asyncio
async def test_merge_findings_uses_index_for_same_title_different_root_causes():
    from learn_kg.merge import merge_findings

    a = ExtractedFinding(**finding_args(title="Shared title", root_cause="external call before balance update"))
    b = ExtractedFinding(**finding_args(title="Shared title", root_cause="missing caller authorization", category="Access Control", subcategory="Missing Input Validation"))
    results = await merge_findings(
        MockLLMClient([[{"new_finding_index": 0, "new_finding_title": "Shared title", "target_ids": [7]}, {"new_finding_index": 1, "new_finding_title": "Shared title", "target_ids": []}]]),
        [a, b],
        [{"id": 7, "title": "canonical reentrancy"}],
    )
    assert results[0].decision.target_ids == [7]
    assert results[1].decision.target_ids == []


@pytest.mark.asyncio
async def test_merge_findings_ignores_title_only_decision_for_ambiguous_titles():
    from learn_kg.merge import merge_findings

    a = ExtractedFinding(**finding_args(title="Shared title", root_cause="external call before balance update"))
    b = ExtractedFinding(**finding_args(title="Shared title", root_cause="missing caller authorization", category="Access Control", subcategory="Missing Input Validation"))
    results = await merge_findings(
        MockLLMClient([[{"new_finding_title": "Shared title", "target_ids": [7]}]]),
        [a, b],
        [{"id": 7, "title": "canonical"}],
    )
    assert results[0].decision.target_ids == []
    assert results[1].decision.target_ids == []

@pytest.mark.asyncio
async def test_merge_findings_ignores_out_of_range_index_for_ambiguous_titles():
    from learn_kg.merge import merge_findings

    a = ExtractedFinding(**finding_args(title="Shared title", root_cause="external call before balance update"))
    b = ExtractedFinding(**finding_args(title="Shared title", root_cause="missing caller authorization", category="Access Control", subcategory="Missing Input Validation"))
    results = await merge_findings(
        MockLLMClient([[{"new_finding_index": 99, "new_finding_title": "Shared title", "target_ids": [7]}]]),
        [a, b],
        [{"id": 7, "title": "canonical"}],
    )
    assert results[0].decision.target_ids == []
    assert results[1].decision.target_ids == []
