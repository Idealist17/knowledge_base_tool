import pytest

from learn_kg.extract import extract_semantics
from learn_kg.llm_client import MockLLMClient
from learn_kg.models import ProjectData, SourceFile


@pytest.mark.asyncio
async def test_extract_semantics_uses_report_semantic_and_finish(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    llm = MockLLMClient([
        [
            {
                "tool": "report_semantic",
                "args": {
                    "name": "Withdrawal Accounting",
                    "category": "Lending",
                    "definition": "A withdrawal path settles user shares into outbound assets.",
                    "description": "The path reads account balance state, checks caller authorization, and performs an outbound asset transfer after validating available liquidity.",
                    "functions": [{"contract_path": "src/Vault.sol", "function_name": "withdraw"}],
                },
            },
            {"tool": "finish", "args": {"summary": "one semantic"}},
        ]
    ])

    out = await extract_semantics(llm, project, ["Lending"])

    assert len(out) == 1
    assert out[0].name == "Withdrawal Accounting"
    assert out[0].functions[0].contract_path == "src/Vault.sol"
    assert "report_semantic" in llm.prompts[0]
    assert "finish" in llm.prompts[0]
    assert "Do not answer with prose or raw JSON" in llm.prompts[0]
    assert "storage slots or mappings" in llm.prompts[0]


@pytest.mark.asyncio
async def test_extract_semantics_allows_empty_chunk_result(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/OnlyViews.sol", content="contract OnlyViews { function x() external pure returns(uint){return 1;} }")],
    )
    out = await extract_semantics(MockLLMClient([[{"tool": "finish", "args": {"summary": "none"}}]]), project, ["Others"])
    assert out == []


@pytest.mark.asyncio
async def test_extract_semantics_dedupes_agentic_reports(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} function exit() external {} }")],
    )
    llm = MockLLMClient([
        [
            {
                "tool": "report_semantic",
                "args": {
                    "name": "Withdrawal Accounting",
                    "category": "Lending",
                    "definition": "short",
                    "description": "short",
                    "functions": [{"contract_path": "src/Vault.sol", "function_name": "withdraw"}],
                },
            },
            {
                "tool": "report_semantic",
                "args": {
                    "name": "withdrawal accounting",
                    "category": "Lending",
                    "definition": "longer definition",
                    "description": "longer description with more concrete behaviour",
                    "functions": [{"contract_path": "src/Vault.sol", "function_name": "exit"}],
                },
            },
            {"tool": "finish", "args": {}},
        ]
    ])

    out = await extract_semantics(llm, project, ["Lending"])

    assert len(out) == 1
    assert out[0].definition == "longer definition"
    assert {f.function_name for f in out[0].functions} == {"withdraw", "exit"}


@pytest.mark.asyncio
async def test_extract_semantics_rejects_missing_finish(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    with pytest.raises(RuntimeError, match="without finish|before calling finish"):
        await extract_semantics(MockLLMClient([[{"tool": "report_semantic", "args": {"name": "S", "category": "Lending", "definition": "d", "description": "d", "functions": [{"contract_path": "A.sol", "function_name": "f"}]}}]]), project, ["Lending"])

@pytest.mark.asyncio
async def test_extract_semantics_rejects_invalid_report_even_if_finish_follows(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    llm = MockLLMClient([[
        {"tool": "report_semantic", "args": {"name": "Bad", "category": "Lending", "definition": "d", "description": "d", "functions": []}},
        {"tool": "finish", "args": {}},
    ]])
    with pytest.raises(RuntimeError, match="invalid semantics|before calling finish|scripted tool calls"):
        await extract_semantics(llm, project, ["Lending"])


@pytest.mark.asyncio
async def test_extract_semantics_rejects_category_outside_project_categories(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    llm = MockLLMClient([[
        {"tool": "report_semantic", "args": {"name": "S", "category": "Dexes", "definition": "d", "description": "d", "functions": [{"contract_path": "src/Vault.sol", "function_name": "withdraw"}]}},
        {"tool": "finish", "args": {}},
    ]])
    with pytest.raises(RuntimeError, match="category"):
        await extract_semantics(llm, project, ["Lending"])


@pytest.mark.asyncio
async def test_extract_semantics_prompt_includes_rust_constraints(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    llm = MockLLMClient([[{"tool": "finish", "args": {}}]])
    await extract_semantics(llm, project, ["Lending"])
    prompt = llm.prompts[0]
    assert "Domain guide" in prompt
    assert "For example, rewrite" in prompt
    assert "read-only helpers" in prompt
    assert "Do not call any tool after finish" in prompt

@pytest.mark.asyncio
async def test_extract_semantics_rejects_report_after_finish_in_same_script(tmp_path):
    project = ProjectData(
        name="p",
        root_dir=tmp_path,
        source_files=[SourceFile(path="src/Vault.sol", content="contract Vault { function withdraw() external {} }")],
    )
    llm = MockLLMClient([[
        {"tool": "finish", "args": {}},
        {"tool": "report_semantic", "args": {"name": "Late", "category": "Lending", "definition": "d", "description": "d", "functions": [{"contract_path": "src/Vault.sol", "function_name": "withdraw"}]}},
    ]])
    with pytest.raises(RuntimeError, match="already finished|invalid semantics"):
        await extract_semantics(llm, project, ["Lending"])


def test_semantic_tool_schema_requires_python_function_field_names():
    from learn_kg.prompts import semantic_tools_schema

    report_tool = next(t for t in semantic_tools_schema() if t["function"]["name"] == "report_semantic")
    fn_schema = report_tool["function"]["parameters"]["properties"]["functions"]["items"]
    assert fn_schema["required"] == ["contract_path", "function_name"]
    assert "contract_path" in fn_schema["properties"]
    assert "function_name" in fn_schema["properties"]
    assert fn_schema["additionalProperties"] is False
