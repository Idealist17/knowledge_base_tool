import pytest
from pathlib import Path
from sqlalchemy import select
from learn_kg.db import HistoricalDatabase
from learn_kg.c4_loader import load_c4_project
from learn_kg.llm_client import MockLLMClient
from learn_kg.pipeline import learn_projects
from learn_kg import schema as s


@pytest.mark.asyncio
async def test_pipeline_two_projects_mock_merge(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}"); db.init()
    p1 = load_c4_project(Path("tests/fixtures/c4"), 1)
    p2 = load_c4_project(Path("tests/fixtures/c4"), 2)
    responses = [
        ["Lending"],
        [{"tool":"report_semantic","args":{"name":"ETH Withdrawal Accounting","category":"Lending","definition":"withdraw accounting","description":"external transfer and balance update","functions":[{"contract_path":"src/Vault.sol","function_name":"withdraw"}]}},{"tool":"finish","args":{"summary":"done"}}],
        [{"tool":"report_finding","args":{"title":"Reentrant withdraw","severity":"High","category":"Reentrancy","subcategory":"Reentrancy Vulnerability with ETH Transfer","root_cause":"external call before balance update","description":"desc","patterns":"call before state","exploits":"repeat withdraw"}},{"tool":"finish","args":{"summary":"done"}}],
        [{"semantic_index":0,"finding_index":0,"strength":"High","evidence":"withdraw reentrancy"}],
        [{"new_semantic_name":"ETH Withdrawal Accounting","target_ids":[],"reason":"new"}],
        [{"new_finding_title":"Reentrant withdraw","target_ids":[],"reason":"new"}],
        ["Lending"],
        [{"tool":"report_semantic","args":{"name":"ETH Withdrawal Accounting","category":"Lending","definition":"withdraw accounting","description":"external transfer and share update","functions":[{"contract_path":"src/Pool.sol","function_name":"exit"}]}},{"tool":"finish","args":{"summary":"done"}}],
        [{"tool":"report_finding","args":{"title":"Reentrant exit","severity":"High","category":"Reentrancy","subcategory":"Reentrancy Vulnerability with ETH Transfer","root_cause":"external call before share update","description":"desc","patterns":"call before state","exploits":"repeat exit"}},{"tool":"finish","args":{"summary":"done"}}],
        [{"semantic_index":0,"finding_index":0,"strength":"High","evidence":"exit reentrancy"}],
        [{"new_semantic_name":"ETH Withdrawal Accounting","target_ids":[1],"appended_description":"pool variant","reason":"same pattern"}],
        [{"new_finding_title":"Reentrant exit","target_ids":[1],"appended_description":"pool variant","reason":"same root cause"}],
    ]
    await learn_projects(db, MockLLMClient(responses), [p1, p2], concurrency=2)
    with db.Session() as session:
        assert session.scalar(select(s.SemanticMerge.to_semantic_id).where(s.SemanticMerge.from_semantic_id == 2)) == 1
        assert session.scalar(select(s.FindingMerge.to_finding_id).where(s.FindingMerge.from_finding_id == 2)) == 1
        assert session.scalar(select(s.SemanticFindingLink.evidence).where(s.SemanticFindingLink.semantic_node_id == 2)) == "exit reentrancy"


@pytest.mark.asyncio
async def test_pipeline_uses_extracted_semantic_categories_for_merge_candidates(tmp_path):
    db = HistoricalDatabase(f"sqlite:///{tmp_path/'kg.sqlite3'}"); db.init()
    p1 = load_c4_project(Path("tests/fixtures/c4"), 1)
    p2 = load_c4_project(Path("tests/fixtures/c4"), 2)
    responses = [
        ["Derivatives"],
        [{"tool":"report_semantic","args":{"name":"Option Exercise Settlement","category":"Derivatives","definition":"d","description":"first option settlement","functions":[{"contract_path":"src/Vault.sol","function_name":"withdraw"}]}},{"tool":"finish","args":{}}],
        [{"tool":"finish","args":{}}],
        [{"new_semantic_name":"Option Exercise Settlement","target_ids":[],"reason":"new"}],
        ["Services"],
        [{"tool":"report_semantic","args":{"name":"Option Exercise Settlement","category":"Derivatives","definition":"d","description":"second option settlement","functions":[{"contract_path":"src/Pool.sol","function_name":"exit"}]}},{"tool":"finish","args":{}}],
        [{"tool":"finish","args":{}}],
        [{"new_semantic_name":"Option Exercise Settlement","target_ids":[1],"reason":"same derivative semantic"}],
    ]

    await learn_projects(db, MockLLMClient(responses), [p1, p2], concurrency=1)

    with db.Session() as session:
        assert session.scalar(select(s.SemanticMerge.to_semantic_id).where(s.SemanticMerge.from_semantic_id == 2)) == 1
