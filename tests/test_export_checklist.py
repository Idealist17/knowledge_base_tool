from pathlib import Path

from typer.testing import CliRunner

from learn_kg.cli import app
from learn_kg.db import HistoricalDatabase, write_project_completed
from learn_kg.export_checklist import (
    ChecklistDocument,
    ChecklistFinding,
    MatchedHistoricalSemantic,
    ProjectSemanticChecklist,
    build_project_checklist,
    fetch_semantic_findings,
    render_checklist_markdown,
)
from learn_kg.llm_client import MockLLMClient
from learn_kg.models import (
    ExtractedFinding,
    ExtractedSemantic,
    FindingMergeDecision,
    FindingMergeResult,
    InProjectLink,
    ProjectData,
    SourceFile,
    SemanticFunction,
    SemanticMergeDecision,
    SemanticMergeResult,
)
from learn_kg.taxonomy import DeFiCategory, VulnerabilityCategory


def sem(name="Withdraw Accounting"):
    return ExtractedSemantic(
        name=name,
        category=DeFiCategory.Lending,
        definition="Controls withdraw accounting",
        description="desc",
        functions=[SemanticFunction(contract_path="src/Vault.sol", function_name="withdraw")],
    )


def finding(title="Reentrant withdraw"):
    return ExtractedFinding(
        title=title,
        severity="High",
        category=VulnerabilityCategory.Reentrancy,
        subcategory="Reentrancy Vulnerability with ETH Transfer",
        root_cause="external call before state update",
        description="desc",
        patterns="state update after external call",
        exploits="reenter withdraw repeatedly",
    )


def seed_historical_linked_finding(db: HistoricalDatabase, tmp_path: Path) -> None:
    p = ProjectData(name="hist", platform_id="hist", root_dir=tmp_path, source_files=[])
    with db.Session() as session, session.begin():
        write_project_completed(
            session,
            p,
            [DeFiCategory.Lending],
            [SemanticMergeResult(semantic=sem("Historical Withdraw"), decision=SemanticMergeDecision(new_semantic_name="Historical Withdraw"))],
            [FindingMergeResult(finding=finding(), decision=FindingMergeDecision(new_finding_title="Reentrant withdraw"))],
            [InProjectLink(semantic_index=0, finding_index=0, evidence="same withdraw flow")],
        )


def test_summary_dedupes_historical_semantics():
    doc = ChecklistDocument(
        project_name="new-proj",
        groups=[
            ProjectSemanticChecklist(semantic=sem("A"), matched_semantics=[MatchedHistoricalSemantic(1, "Hist", "High", "same", [])]),
            ProjectSemanticChecklist(semantic=sem("B"), matched_semantics=[MatchedHistoricalSemantic(1, "Hist", "High", "same", [])]),
        ],
    )

    assert doc.historical_semantics_matched == 1


def test_render_checklist_markdown_sanitizes_single_line_fields():
    doc = ChecklistDocument(
        project_name="new\nproj",
        groups=[
            ProjectSemanticChecklist(
                semantic=sem("Withdraw\nAccounting"),
                matched_semantics=[MatchedHistoricalSemantic(1, "Historical\nWithdraw", "High", "same", [ChecklistFinding("F1\nextra", "High", "root", "pattern", "exploit", "High", "kg")])],
            )
        ],
    )

    md = render_checklist_markdown(doc)

    assert "# Audit Checklist: new proj" in md
    assert "## Withdraw Accounting" in md
    assert "### Matched historical semantic: Historical Withdraw" in md
    assert "- [ ] Check whether: F1 extra" in md


def test_render_empty_semantics_has_explicit_manual_review():
    md = render_checklist_markdown(ChecklistDocument(project_name="empty", groups=[]))

    assert "- Project semantics analyzed: 0" in md
    assert "## No project semantics extracted" in md
    assert "- [ ] Manually review this project; semantic extraction produced no checklist groups." in md


def test_render_checklist_markdown_summary_and_multiple_findings():
    doc = ChecklistDocument(
        project_name="new-proj",
        groups=[
            ProjectSemanticChecklist(
                semantic=sem(),
                matched_semantics=[
                    MatchedHistoricalSemantic(
                        semantic_id=1,
                        name="Historical Withdraw",
                        match_strength="High",
                        match_evidence="same accounting purpose",
                        findings=[
                            ChecklistFinding("F1", "High", "root 1", "pattern 1", "exploit 1", "High", "kg evidence 1"),
                            ChecklistFinding("F2", "Medium", "root 2", "pattern 2", "exploit 2", "Medium", "kg evidence 2"),
                        ],
                    )
                ],
            )
        ],
    )

    md = render_checklist_markdown(doc)

    assert "# Audit Checklist: new-proj" in md
    assert "- Project semantics analyzed: 1" in md
    assert "- Historical semantics matched: 1" in md
    assert "- Checklist items: 2" in md
    assert "## Withdraw Accounting" in md
    assert "### Matched historical semantic: Historical Withdraw" in md
    assert "- Match strength: High" in md
    assert "- [ ] Check whether: F1" in md
    assert "  - KG evidence: kg evidence 2" in md


def test_fetch_semantic_findings_reads_link_evidence(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    seed_historical_linked_finding(db, tmp_path)

    links = fetch_semantic_findings(db, [1])

    assert links[1][0].title == "Reentrant withdraw"
    assert links[1][0].severity == "High"
    assert links[1][0].root_cause == "external call before state update"
    assert links[1][0].risk_pattern == "state update after external call"
    assert links[1][0].exploit_shape == "reenter withdraw repeatedly"
    assert links[1][0].kg_link_strength == "High"
    assert links[1][0].kg_evidence == "same withdraw flow"


def test_fetch_semantic_findings_includes_merged_child_links(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    seed_historical_linked_finding(db, tmp_path)
    p2 = ProjectData(name="hist2", platform_id="hist2", root_dir=tmp_path, source_files=[])
    with db.Session() as session, session.begin():
        write_project_completed(
            session,
            p2,
            [DeFiCategory.Lending],
            [SemanticMergeResult(semantic=sem("Historical Child"), decision=SemanticMergeDecision(new_semantic_name="Historical Child", target_ids=[1]))],
            [FindingMergeResult(finding=finding("Child linked finding"), decision=FindingMergeDecision(new_finding_title="Child linked finding"))],
            [InProjectLink(semantic_index=0, finding_index=0, evidence="child semantic link")],
        )

    links = fetch_semantic_findings(db, [1])

    assert [item.title for item in links[1]] == ["Reentrant withdraw", "Child linked finding"]
    assert links[1][1].kg_evidence == "child semantic link"


def test_build_project_checklist_integrates_semantic_matching(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    seed_historical_linked_finding(db, tmp_path)
    project = ProjectData(name="new-proj", root_dir=tmp_path, source_files=[SourceFile(path="Vault.sol", content="contract Vault { function withdraw() external {} }", language="solidity")])
    llm = MockLLMClient([
        [{"category": "Lending"}],
        [
            {"tool": "report_semantic", "args": sem().model_dump(mode="json")},
            {"tool": "finish", "args": {"summary": "done"}},
        ],
        [{"new_semantic_name": "Withdraw Accounting", "target_ids": [1], "reason": "same accounting purpose"}],
    ])
    before = db.counts()

    doc = __import__("asyncio").run(build_project_checklist(db, llm, project))
    md = render_checklist_markdown(doc)

    assert doc.project_semantics_analyzed == 1
    assert doc.historical_semantics_matched == 1
    assert "## Withdraw Accounting" in md
    assert "### Matched historical semantic: Historical Withdraw" in md
    assert "- Match evidence: same accounting purpose" in md
    assert "- [ ] Check whether: Reentrant withdraw" in md
    assert db.counts() == before


def test_empty_match_still_outputs_manual_review(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    project = ProjectData(name="new-proj", root_dir=tmp_path, source_files=[SourceFile(path="Vault.sol", content="contract Vault { function withdraw() external {} }", language="solidity")])
    llm = MockLLMClient([
        [{"category": "Lending"}],
        [
            {"tool": "report_semantic", "args": sem().model_dump(mode="json")},
            {"tool": "finish", "args": {"summary": "done"}},
        ],
        [{"new_semantic_name": "Withdraw Accounting", "target_ids": [], "reason": "no match"}],
    ])

    doc = __import__("asyncio").run(build_project_checklist(db, llm, project))
    md = render_checklist_markdown(doc)

    assert doc.project_semantics_analyzed == 1
    assert doc.historical_semantics_matched == 0
    assert doc.checklist_items == 1
    assert "### Matched historical semantic: None" in md
    assert "- [ ] Manually review this semantic; no historical finding links were matched." in md


def test_cli_checklist_writes_markdown_and_does_not_mutate_db(tmp_path, monkeypatch):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}")
    db.init()
    seed_historical_linked_finding(db, tmp_path)
    before = db.counts()
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "Vault.sol").write_text("contract Vault { function withdraw() external {} }", encoding="utf-8")
    out = tmp_path / "checklist.md"

    async def fake_export(kg, llm, project, out_path, *, config=None, logger=None):
        doc = ChecklistDocument(project_name=project.name, groups=[ProjectSemanticChecklist(semantic=sem(), matched_semantics=[])])
        out_path.write_text(render_checklist_markdown(doc), encoding="utf-8")
        return doc

    monkeypatch.setattr("learn_kg.cli.export_project_checklist", fake_export)
    result = CliRunner().invoke(app, ["checklist", "--db", f"sqlite:///{tmp_path/'kg.sqlite3'}", "--project", f"new:{project_dir}", "--out", str(out), "--quiet"])

    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "# Audit Checklist: new" in out.read_text(encoding="utf-8")
    assert db.counts() == before


def test_cli_checklist_rejects_missing_sqlite_without_creating_file(tmp_path):
    missing_db = tmp_path / "missing.sqlite3"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    out = tmp_path / "checklist.md"

    result = CliRunner().invoke(app, ["checklist", "--db", f"sqlite:///{missing_db}", "--project", f"new:{project_dir}", "--out", str(out), "--quiet"])

    assert result.exit_code != 0
    assert "SQLite database does not exist" in result.output
    assert not missing_db.exists()
