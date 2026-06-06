from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class DeFiCategory(str, Enum):
    Lending = "Lending"
    Dexes = "Dexes"
    Yield = "Yield"
    Services = "Services"
    Derivatives = "Derivatives"
    YieldAggregator = "Yield Aggregator"
    RealWorldAssets = "Real World Assets"
    Stablecoins = "Stablecoins"
    Indexes = "Indexes"
    Insurance = "Insurance"
    NftMarketplace = "NFT Marketplace"
    NftLending = "NFT Lending"
    CrossChain = "Cross Chain"
    Others = "Others"


class VulnerabilityCategory(str, Enum):
    AccessControl = "Access Control"
    Arithmetic = "Arithmetic"
    BlockManipulation = "Block Manipulation"
    Cryptographic = "Cryptographic"
    DenialOfServices = "Denial of Services"
    Reentrancy = "Reentrancy"
    StorageAndMemory = "Storage & Memory"


@dataclass(frozen=True)
class TaxonomyEntry:
    category: VulnerabilityCategory
    subcategory: str
    description: str


_RAW_TAXONOMY = [
    (VulnerabilityCategory.AccessControl, 'Arbitrary `from` in transferFrom() without msg.sender Check', 'Detect when transferFrom uses an arbitrary from address without validating msg.sender.'),
    (VulnerabilityCategory.AccessControl, 'Call to Arbitrary Addresses with Unchecked Calldata', 'Calling arbitrary addresses with attacker-controlled calldata can trigger unexpected behavior.'),
    (VulnerabilityCategory.AccessControl, 'Caller Not Checked', 'Authorization assumes caller properties that can be bypassed, such as constructor-time extcodesize checks.'),
    (VulnerabilityCategory.AccessControl, 'Contract Could be Destructed', 'A privileged or unguarded path can destruct the contract or logic contract.'),
    (VulnerabilityCategory.AccessControl, 'Dangerous Immediate Initialization of State Variables', 'State is initialized through unsafe non-constant calls or mutable state dependencies.'),
    (VulnerabilityCategory.AccessControl, 'Dangerous Usage of `tx.origin`', 'Authorization depends on tx.origin and can be abused through call relays.'),
    (VulnerabilityCategory.AccessControl, 'Default Function Visibility', 'Missing explicit visibility exposes state-changing functions publicly.'),
    (VulnerabilityCategory.AccessControl, 'Initializing Method without Permission Check', 'Initialization can be triggered without an adequate permission check.'),
    (VulnerabilityCategory.AccessControl, 'Method permit() Used for Arbitrary `from` in transferFrom()', 'permit-based flows allow arbitrary transferFrom source selection without validating the true owner.'),
    (VulnerabilityCategory.AccessControl, 'Missing `msg.sender` Check for transferFrom()', 'transferFrom uses an attacker-controlled from address instead of binding to msg.sender or equivalent authorization.'),
    (VulnerabilityCategory.AccessControl, 'Missing Input Validation', 'Critical input values such as addresses, ids, chain selectors, or enum values are not validated.'),
    (VulnerabilityCategory.AccessControl, 'Sending Ether to Arbitrary Destinations', 'Ether can be sent to attacker-controlled destinations due to insufficient validation.'),
    (VulnerabilityCategory.AccessControl, 'Unprotected Contract Destruction', 'selfdestruct or equivalent destructive behavior is reachable without adequate protection.'),
    (VulnerabilityCategory.AccessControl, 'Unprotected Ether Withdrawal', 'Ether withdrawal paths are exposed without adequate access control or accounting.'),
    (VulnerabilityCategory.AccessControl, 'Unsafe Delegatecall', 'delegatecall is performed against unsafe or attacker-controlled targets.'),
    (VulnerabilityCategory.AccessControl, 'Unused Return Value', 'A critical external call return value is ignored, hiding failure or authorization problems.'),
    (VulnerabilityCategory.AccessControl, 'Usage of public mint or burn', 'Mint or burn functionality is exposed publicly or without sufficient authorization.'),
    (VulnerabilityCategory.AccessControl, 'Write to Arbitrary Storage Location', 'An attacker can influence writes to arbitrary storage slots or equivalent protected state.'),
    (VulnerabilityCategory.Arithmetic, 'Inappropriate Integer Division before Multiplication', 'Integer division before multiplication truncates precision and causes incorrect accounting.'),
    (VulnerabilityCategory.Arithmetic, 'Integer Overflow', 'Arithmetic can overflow and wrap or revert in a way that breaks intended invariants.'),
    (VulnerabilityCategory.Arithmetic, 'Integer Underflow', 'Arithmetic can underflow and wrap or revert in a way that breaks intended invariants.'),
    (VulnerabilityCategory.Arithmetic, 'Unsafe Array Length Assignment', 'User-controlled inputs can influence array length assignments or equivalent bounds changes.'),
    (VulnerabilityCategory.BlockManipulation, 'Dangerous Usage of `block.timestamp`', 'Security-critical logic depends on block.timestamp or similarly manipulable block metadata.'),
    (VulnerabilityCategory.BlockManipulation, 'Transaction Order Dependency', 'Correctness or fairness depends on transaction ordering and can be manipulated by frontrunning or reordering.'),
    (VulnerabilityCategory.BlockManipulation, 'Weak PRNG (Pseudorandom Number Generator)', 'Randomness depends on predictable or miner-influenced blockchain values.'),
    (VulnerabilityCategory.Cryptographic, 'Lack of Proper Signature Verification', 'Signed messages are accepted without sufficient signer, domain, nonce, or intent validation.'),
    (VulnerabilityCategory.Cryptographic, 'Signature Malleability', 'Signatures can be altered into alternative valid encodings and replayed or mis-accounted.'),
    (VulnerabilityCategory.DenialOfServices, '`transfer()` and `send()` with Hardcoded Gas Amount', 'Value transfer relies on fixed gas forwarding assumptions that can break protocol liveness.'),
    (VulnerabilityCategory.DenialOfServices, 'Contract Could Lock Ether', 'Funds can become permanently locked because the contract has no viable withdrawal or escape path.'),
    (VulnerabilityCategory.DenialOfServices, 'DoS with Block Gas Limit', 'Unbounded work or data growth can push execution beyond the block gas limit.'),
    (VulnerabilityCategory.DenialOfServices, 'DoS With Failed Call', 'A failed external call can block progress or cause protocol-wide denial of service.'),
    (VulnerabilityCategory.DenialOfServices, 'Force Sending Ether with this.balance check in require() or assert()', 'Force-sent ether can break logic that relies on exact balance checks.'),
    (VulnerabilityCategory.DenialOfServices, 'Unsafe send() in the require() Condition', 'send inside a require/assert style condition can be weaponized to revert protocol progress.'),
    (VulnerabilityCategory.Reentrancy, 'Reentrancy Vulnerability with Negative Events', 'External control flow can reenter before state is safely updated, leading to invalid negative-state effects.'),
    (VulnerabilityCategory.Reentrancy, 'Reentrancy Vulnerability with Transfer', 'An external transfer opens a reentrant path before invariant-preserving state updates complete.'),
    (VulnerabilityCategory.Reentrancy, 'Reentrancy Vulnerability with Same Effect', 'Reentrancy repeats the same state transition or accounting effect multiple times.'),
    (VulnerabilityCategory.Reentrancy, 'Reentrancy Vulnerability with ETH Transfer', 'ETH transfer creates a callback path that can reenter before state is finalized.'),
    (VulnerabilityCategory.Reentrancy, 'Reentrancy Vulnerability without ETH Transfer', 'An external call without direct ETH transfer still enables reentrant state corruption.'),
    (VulnerabilityCategory.StorageAndMemory, 'Arbitrary Function Jump via Inline Assembly', 'Inline assembly can redirect execution or corrupt function pointers or equivalent dispatch state.'),
    (VulnerabilityCategory.StorageAndMemory, 'Bytes Variables Risk', 'Improper ABI-decoding or bytes handling causes ambiguous values, truncation, or collision-like behavior.'),
    (VulnerabilityCategory.StorageAndMemory, 'Dangerous Usage of `msg.value` inside a Loop', 'msg.value is reused inside loops and causes repeated accounting or payout errors.'),
    (VulnerabilityCategory.StorageAndMemory, 'Error-prone Assembly Usage', 'Low-level assembly is used in a way that can corrupt state or bypass invariants.'),
    (VulnerabilityCategory.StorageAndMemory, 'Memory Manipulation', 'Unsafe memory access or mutation causes incorrect behavior, corruption, or exploitable state transitions.'),
    (VulnerabilityCategory.StorageAndMemory, 'Modifying storage array by value', 'Storage arrays are handled with the wrong copy/reference semantics and cause unintended mutation.'),
    (VulnerabilityCategory.StorageAndMemory, 'Payable Functions using `delegatecall` inside a Loop', 'delegatecall in a payable loop can multiply accounting effects or corrupt balance tracking.'),
]

FINDING_TAXONOMY: tuple[TaxonomyEntry, ...] = tuple(TaxonomyEntry(*row) for row in _RAW_TAXONOMY)


def all_defi_categories() -> list[DeFiCategory]:
    return list(DeFiCategory)


def all_taxonomy_entries() -> list[TaxonomyEntry]:
    return list(FINDING_TAXONOMY)


def taxonomy_prompt() -> str:
    out = ["Choose exactly one vulnerability category and one subcategory from the taxonomy below.", ""]
    current: VulnerabilityCategory | None = None
    for entry in FINDING_TAXONOMY:
        if entry.category != current:
            if current is not None:
                out.append("")
            out.append(f"### {entry.category.value}")
            current = entry.category
        out.append(f"- {entry.subcategory}: {entry.description}")
    return "\n".join(out)


def normalize_taxonomy_key(text: str) -> str:
    return " ".join(re.sub(r"[^0-9A-Za-z]+", " ", text).lower().split())


def coerce_vulnerability_category(category: str | VulnerabilityCategory) -> VulnerabilityCategory | None:
    if isinstance(category, VulnerabilityCategory):
        return category
    for cat in VulnerabilityCategory:
        if normalize_taxonomy_key(cat.value) == normalize_taxonomy_key(str(category)) or normalize_taxonomy_key(cat.name) == normalize_taxonomy_key(str(category)):
            return cat
    return None


def coerce_defi_category(category: str | DeFiCategory) -> DeFiCategory:
    if isinstance(category, DeFiCategory):
        return category
    for cat in DeFiCategory:
        if normalize_taxonomy_key(cat.value) == normalize_taxonomy_key(str(category)) or cat.name == str(category):
            return cat
    return DeFiCategory.Others


def resolve_taxonomy_entry(category: str | VulnerabilityCategory, subcategory: str) -> TaxonomyEntry | None:
    cat = coerce_vulnerability_category(category)
    normalized = normalize_taxonomy_key(subcategory)
    # The LLM sometimes confuses DeFi project category (e.g. "Derivatives") with
    # vulnerability category, while still selecting a valid taxonomy
    # subcategory. Prefer an exact category+subcategory match when possible, but
    # fall back to a globally unique subcategory match to recover the canonical
    # vulnerability category.
    global_matches = []
    for entry in FINDING_TAXONOMY:
        if normalize_taxonomy_key(entry.subcategory) != normalized:
            continue
        if cat is not None and entry.category == cat:
            return entry
        global_matches.append(entry)
    if len(global_matches) == 1:
        return global_matches[0]
    return None


def validate_taxonomy_pair(category: str | VulnerabilityCategory, subcategory: str) -> None:
    if resolve_taxonomy_entry(category, subcategory) is None:
        raise ValueError(f"Unknown vulnerability taxonomy pair: {category} / {subcategory}")
