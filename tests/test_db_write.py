from learn_kg.db import HistoricalDatabase, write_project_completed
from learn_kg.models import ProjectData, ExtractedSemantic, ExtractedFinding, SemanticMergeDecision, FindingMergeDecision, SemanticMergeResult, FindingMergeResult, InProjectLink, SemanticFunction
from learn_kg.taxonomy import DeFiCategory, VulnerabilityCategory
from learn_kg import schema as s
from sqlalchemy import select


def sem(name):
    return ExtractedSemantic(name=name, category=DeFiCategory.Lending, definition="def", description="desc", functions=[SemanticFunction(contract_path="src/Vault.sol", function_name="withdraw")])


def finding(title):
    return ExtractedFinding(title=title, severity="High", category=VulnerabilityCategory.Reentrancy, subcategory="Reentrancy Vulnerability with ETH Transfer", root_cause="external call before state update", description="desc")


def test_write_new_and_pending(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}"); db.init()
    p = ProjectData(name="p1", platform_id="p1", root_dir=tmp_path, source_files=[])
    sr = [SemanticMergeResult(semantic=sem("Withdraw Accounting"), decision=SemanticMergeDecision(new_semantic_name="Withdraw Accounting", target_ids=[]))]
    fr = [FindingMergeResult(finding=finding("Reentrant withdraw"), decision=FindingMergeDecision(new_finding_title="Reentrant withdraw", target_ids=[]))]
    with db.Session() as session, session.begin():
        write_project_completed(session, p, [DeFiCategory.Lending], sr, fr, [InProjectLink(semantic_index=0, finding_index=0, evidence="same flow")])
    with db.Session() as session:
        assert session.scalar(select(s.Project).where(s.Project.name == "p1"))
        assert session.scalar(select(s.PendingSemantic.semantic_node_id)) == 1
        assert session.scalar(select(s.SemanticFindingLink.evidence)) == "same flow"


def test_multi_target_merge(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}"); db.init()
    p1 = ProjectData(name="p1", platform_id="p1", root_dir=tmp_path, source_files=[])
    with db.Session() as session, session.begin():
        write_project_completed(session, p1, [DeFiCategory.Lending], [SemanticMergeResult(semantic=sem("S1"), decision=SemanticMergeDecision(new_semantic_name="S1"))], [FindingMergeResult(finding=finding("F1"), decision=FindingMergeDecision(new_finding_title="F1"))], [])
    p2 = ProjectData(name="p2", platform_id="p2", root_dir=tmp_path, source_files=[])
    with db.Session() as session, session.begin():
        write_project_completed(session, p2, [DeFiCategory.Lending], [SemanticMergeResult(semantic=sem("S2"), decision=SemanticMergeDecision(new_semantic_name="S2", target_ids=[1], appended_description="more"))], [FindingMergeResult(finding=finding("F2"), decision=FindingMergeDecision(new_finding_title="F2", target_ids=[1], appended_description="more"))], [])
    with db.Session() as session:
        assert session.scalar(select(s.SemanticMerge.to_semantic_id).where(s.SemanticMerge.from_semantic_id == 2)) == 1
        assert session.scalar(select(s.FindingMerge.to_finding_id).where(s.FindingMerge.from_finding_id == 2)) == 1
        assert session.get(s.SemanticNode, 1).description.endswith("more")
