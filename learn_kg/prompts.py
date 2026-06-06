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


def defi_category_definitions() -> str:
    return """Protocol-domain guide:

* Dexes: on-chain trading venues, whether pool based, curve based, auction based, or order-book based.
* Derivatives: options, perpetuals, synthetic exposure, structured payoff, and other contracts whose value follows another asset or index.
* Stablecoins: minting, redemption, peg management, reserve accounting, or other stable-value token systems.
* Lending: collateral deposits, debt creation, interest accrual, liquidations, credit delegation, or repay/withdraw flows.
* Yield: staking, locking, reward emission, checkpointing, vesting, and incentive distribution.
* Yield Aggregator: vault or strategy layers that route capital into one or more yield sources for users.
* Services: supporting infrastructure such as oracle, automation, privacy, account, registry, keeper, or routing services.
* Real World Assets: tokenized off-chain claims, collateral, invoices, securities, commodities, or similar real-world positions.
* NFT Marketplace: listing, bidding, auction, royalty, escrow, or settlement flows for non-fungible assets.
* NFT Lending: borrowing, lending, rental, foreclosure, or collateral management where NFTs are the primary collateral.
* Cross Chain: bridge accounting, message passing, remote execution, lock/mint, burn/release, or cross-domain synchronization.
* Others: use only for mechanics that do not naturally fit one of the domains above.
"""


def semantic_extract_system_prompt() -> str:
    return (
        "You are an expert DeFi knowledge engineer and senior smart contract analyst. "
        "Follow the user's instructions exactly. Use canonical, project-agnostic DeFi terminology. "
        "When tools are available, record structured results only through tool calls."
    )


def semantic_extract_prompt(project: ProjectData, chunk: str, categories: list[str]) -> str:
    return f"""You are reviewing one bounded slice of smart-contract source.
Base the extraction only on this slice; do not infer behaviour from outside context.
Project-level domains already assigned: {categories}
Use the domain guide when selecting the category for each reported item.

## Domain guide

{defi_category_definitions()}

## Code slice

{chunk}

## Extraction objective

Identify reusable DeFi business behaviours in this code slice. Each behaviour should be described so that it can be matched against another protocol later without relying on this project's names.

For every reported semantic, provide:
1. name: a compact generic label, such as "Reserve-backed redemption" or "Signed order settlement".
2. definition: one precise sentence describing the behaviour class.
3. description: implementation-aware prose, normally 4-8 sentences. Prefer concrete mechanics over broad labels. When the code shows them, capture the storage slots or mappings touched, whether updates are additive/replacement/checkpoint-based, the caller or role gate, checks and revert conditions, external calls and how failures propagate, invariants being maintained, and the before/after state of the flow.
4. functions: source anchors using the exact Python schema fields contract_path and function_name. This is the only place where file paths and real function identifiers belong. Provide at least one anchor.
5. category: one category from the assigned project domains; choose "Others" only when the behaviour cannot be placed in those domains.

## Critical Rules

1. Hard rule on abstraction: name, definition, and description MUST NOT include project-specific names. Use only generic DeFi roles. For example, rewrite project-specific phrasing into role-based phrasing.
   - Bad: "Deposit into BentoBox to mint BentoShares".
   - Good: "Deposit into shared vault to mint unified liquidity shares".
2. Do not include specific protocol or project names in name, definition, or description.
   - Bad: "Uniswap pool swap settlement".
   - Good: "constant-product pool swap settlement".
3. Do not include specific contract names in name, definition, or description; keep them only in functions.contract_path when needed for source anchoring.
   - Bad: "UniswapV2Pair reserve update".
   - Good: "pair reserve update".
4. Do not include specific function signatures or library API names in name, definition, or description; keep the real entry point only in functions.function_name.
   - Bad: "swapExactTokensForTokens(...) computes output before transfer".
   - Good: "the swap entry point computes output before the inbound transfer".
5. Do not include specific branded asset names in name, definition, or description.
   - Bad: "accepts ETH and wraps it into WETH".
   - Good: "accepts the native asset and wraps it into a wrapped native asset".
   - Bad: "transfers USDC collateral".
   - Good: "transfers stablecoin collateral".
6. Use canonical DeFi vocabulary where it fits.
   - Bad: "handles money moving stuff".
   - Good: "escrow settlement", "liquidity provision", "debt position", "vault share", or "invariant-preserving swap".
7. Group by business meaning, not by syntax. Submit same-meaning entry points together in one report_semantic call.
   - Bad: separate semantics for mint, burn, _mint, and _burn when they are all token supply updates.
   - Good: one "Fungible token supply adjustment" semantic with all related functions listed.
8. Fold admin, read-only helpers, governance plumbing, and ordinary token boilerplate into one Utility/Admin item for the slice instead of many tiny items.
   - Bad: one semantic for setFee, one for setBaseURI, one for domainSeparator.
   - Good: one "Utility/Admin configuration and helpers" semantic.
9. Cover all relevant callable/public entry points visible in this slice, even if another chunk may repeat them later.
   - Bad: skipping a settlement entry point because a later chunk may include it again.
   - Good: report it now and let cross-chunk merging deduplicate later.

The functions field is the only place where real file paths and function identifiers belong. It SHOULD keep the exact Python schema fields contract_path and function_name.

## Required tool protocol

Do not answer with prose or raw JSON.
- Submit each distinct behaviour with report_semantic.
- When the slice is fully handled, call finish once.
- If there is nothing meaningful to report, call finish without report_semantic.
- Do not call any tool after finish.
"""

def semantic_tools_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "report_semantic",
                "description": "Record one project-agnostic DeFi semantic extracted from the current source chunk.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "category": {"type": "string"},
                        "definition": {"type": "string"},
                        "description": {"type": "string"},
                        "functions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "contract_path": {"type": "string"},
                                    "function_name": {"type": "string"},
                                },
                                "required": ["contract_path", "function_name"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "category", "definition", "description", "functions"],
                    "additionalProperties": True,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Signal that semantic extraction for this chunk is complete. Call exactly once after all report_semantic calls.",
                "parameters": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "additionalProperties": True,
                },
            },
        },
    ]


def finding_extract_system_prompt() -> str:
    return (
        "You are an expert DeFi knowledge engineer and senior smart contract security analyst. "
        "Follow the user's instructions exactly. Extract vulnerability findings as project-agnostic, "
        "reusable root-cause knowledge. When tools are available, record structured results only through tool calls."
    )


def finding_extract_prompt(project: ProjectData, chunk: str, categories: list[str]) -> str:
    return f"""You are reviewing one bounded audit report excerpt.
Base extraction only on this excerpt; do not infer behaviour from outside context.
Project-level domains are context only and must not be written into finding.category: {categories}

## Vulnerability taxonomy

{taxonomy_prompt()}

## Report excerpt

{chunk}

## Extraction objective

Extract audit findings by independent exploit mechanism or independent root cause. Do not answer with prose or raw JSON.
Submit each finding through report_finding, then call finish once when the excerpt is fully handled.

For every report_finding call, provide these Python-schema fields:
1. title: preserve the original report finding title exactly as written. If one original finding is decomposed into multiple independent mechanisms, reuse the same title for each report_finding call.
2. severity: one of exactly High, Medium, or Low. Map informational/non-security material to finish summary instead of report_finding unless it contains an exploitable mechanism that can be mapped to High/Medium/Low.
3. category and subcategory: both must strictly come from the vulnerability taxonomy above. Do not use project domain categories here.
4. root_cause: the specific technical or economic cause that makes the bug possible. Avoid abstract labels such as "access control issue", "accounting bug", or "validation missing" unless the concrete missing check, stale state, rounding direction, trust boundary, incentive mismatch, or failure propagation is also stated.
5. description: explain the vulnerable state before the action, the state after the action, who can break the intended behaviour, and how the invariant or accounting relationship drifts.
6. patterns: a single string describing reusable detection patterns: relevant state variables, required call ordering, external failure modes, and control-flow decisions.
7. exploits: a single string describing a reproducible attack or failure sequence from setup to impact.

## Critical Rules

0. Keep title unchanged, including protocol, contract, function, or asset names if they are present in the original title. The title is the only field where original report wording is preserved verbatim.
   - Example: if the report title is "USDC withdrawals can lock VaultX", keep that exact title.
1. Hard rule on abstraction: outside the title, root_cause, description, patterns, and exploits MUST NOT include project-specific names. Use only generic security and DeFi roles.
   - Bad: "VaultX calls USDC.transferFrom in withdrawFromVault(...)".
   - Good: "the vault calls an external token transfer in the withdrawal entry point".
2. do not include protocol names or specific project names outside the title.
   - Bad: "Aave market accounting drifts".
   - Good: "lending market accounting drifts".
3. Do not include specific contract names outside the title.
   - Bad: "UniswapV2Pair updates reserves after the callback".
   - Good: "the pair contract updates reserves after the external callback".
4. Do not include specific function signatures or library API names outside the title.
   - Bad: "swapExactTokensForTokens(...) lacks a stale-price guard".
   - Good: "the swap entry point lacks a stale-price guard".
5. Do not include specific branded asset names outside the title.
   - Bad: "USDC transfer reverts and locks WETH collateral".
   - Good: "stablecoin transfer reverts and locks wrapped native-asset collateral".
   - Bad: "stETH share accounting is stale".
   - Good: "wrapped staking receipt share accounting is stale".
6. Keep Python field names exactly as listed above. Do not introduce alternate or Rust-specific field names.
   - Bad: emit function_name/contract anchors or Rust-only field names in report_finding.
   - Good: emit title, severity, category, subcategory, root_cause, description, patterns, and exploits.
7. patterns and exploits must be strings, not arrays or objects.
   - Bad: patterns: ["external call before state update"].
   - Good: patterns: "external call occurs before state update".
8. Prefer concrete state-transition language over broad summaries.
   - Bad: "accounting bug due to missing validation".
   - Good: "the debt index is read before interest accrual, so the repay path burns too few debt shares after the index increases".
9. Atomic decomposition: if one original report finding contains multiple independent mechanisms, call report_finding once per mechanism and share the same original title.
   - Bad: combine "missing owner check" and "zero-address setter bricks withdrawals" into one root cause.
   - Good: emit two findings with the same title and separate root_cause, patterns, and exploits.
10. Do not invent findings that are not supported by this excerpt; if no supported High/Medium/Low finding exists, call finish without report_finding.
   - Bad: infer a reentrancy issue from a generic transfer mention.
   - Good: report only when the excerpt shows the call ordering, state drift, or exploitable precondition.

## Required tool protocol

- Submit each distinct finding with report_finding.
- When the excerpt is fully handled, call finish once.
- If there is nothing meaningful to report, call finish without report_finding.
- Do not call any tool after finish.
"""


def finding_tools_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "report_finding",
                "description": "Record one project-agnostic vulnerability finding extracted from the current audit report excerpt.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "severity": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "category": {"type": "string"},
                        "subcategory": {"type": "string"},
                        "root_cause": {"type": "string"},
                        "description": {"type": "string"},
                        "patterns": {"type": "string"},
                        "exploits": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "severity",
                        "category",
                        "subcategory",
                        "root_cause",
                        "description",
                        "patterns",
                        "exploits",
                    ],
                    "additionalProperties": True,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Signal that finding extraction for this report excerpt is complete. Call exactly once after all report_finding calls.",
                "parameters": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "additionalProperties": True,
                },
            },
        },
    ]


def in_project_link_prompt(semantics: list[ExtractedSemantic], findings: list[ExtractedFinding]) -> str:
    return "Link every finding to at least one semantic by zero-based indexes. Return exactly one JSON object: {\"items\":[{\"semantic_index\":0,\"finding_index\":0,\"strength\":\"High|Medium|Low\",\"evidence\":\"...\"}]}\nSEMANTICS:\n" + json.dumps([x.model_dump(mode='json') for x in semantics], indent=2) + "\nFINDINGS:\n" + json.dumps([x.model_dump(mode='json') for x in findings], indent=2)


def semantic_merge_prompt(new_semantics: list[ExtractedSemantic], canonicals: list[dict]) -> str:
    return "Decide whether each new semantic is NEW or merges to target canonical ids. Support multiple targets. Return exactly one JSON object: {\"items\":[{\"new_semantic_name\":\"...\",\"target_ids\":[1],\"appended_description\":\"...\",\"reason\":\"...\"}]}\nNEW:\n" + json.dumps([x.model_dump(mode='json') for x in new_semantics], indent=2) + "\nCANONICALS:\n" + json.dumps(canonicals, indent=2)


def finding_merge_prompt(new_findings: list[ExtractedFinding], canonicals: list[dict]) -> str:
    indexed_findings = [dict({"index": idx}, **x.model_dump(mode='json')) for idx, x in enumerate(new_findings)]
    return (
        "Decide whether each new finding is NEW or merges to target canonical ids. "
        "Support multiple targets. Findings may share the same title, so you MUST identify each decision by new_finding_index. "
        "Return exactly one JSON object: "
        "{\"items\":[{\"new_finding_index\":0,\"new_finding_title\":\"...\",\"target_ids\":[1],"
        "\"appended_description\":\"...\",\"appended_patterns\":\"...\",\"appended_exploits\":\"...\",\"reason\":\"...\"}]}"
        "\nNEW:\n" + json.dumps(indexed_findings, indent=2) + "\nCANONICALS:\n" + json.dumps(canonicals, indent=2)
    )


def global_link_prompt(findings: list[dict], semantics: list[dict]) -> str:
    return "Link canonical findings to canonical semantics. Omit unrelated pairs. Return exactly one JSON object: {\"items\":[{\"semantic_id\":1,\"finding_id\":1,\"strength\":\"High|Medium|Low\",\"evidence\":\"...\"}]}\nFINDINGS:\n" + json.dumps(findings, indent=2) + "\nSEMANTICS:\n" + json.dumps(semantics, indent=2)
