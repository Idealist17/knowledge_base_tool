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

## Style and grouping rules

- Keep name, definition, and description free of project branding, contract identifiers, function signatures, library API names, and token brand names. Replace them with role-based wording such as collateral vault, reward checkpoint, swap router, settlement adapter, receipt token, signer, keeper, or oracle feed. For example, rewrite a project-specific phrase like "deposit into a named vault to mint named shares" as "deposit into a shared vault to mint accounting shares".
- Use normal DeFi vocabulary where it fits: liquidity provision, debt position, vault share, invariant-preserving swap, range order, reward index, liquidation, escrow settlement, signed intent, and similar terms.
- Group by business meaning, not by syntax. Entry points that implement the same user-visible or accounting behaviour should be submitted together in one report_semantic call. Administrative setters, read-only helpers, governance plumbing, and ordinary token boilerplate should be folded into a single Utility/Admin item for the slice instead of many tiny items.
- Cover all relevant callable/public entry points visible in the slice. Later pipeline stages will merge duplicate cross-chunk output, so do not omit a behaviour merely because it may appear elsewhere.

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
