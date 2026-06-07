# Audit Checklist: c4-3

## Summary
- Project semantics analyzed: 17
- Historical semantics matched: 40
- Checklist items: 103
- Candidate checklist findings considered: 692
- Candidate checklist findings rendered: 100
- Candidate checklist findings deduped: 403
- Candidate checklist findings trimmed by caps: 189

## Maintenance stake escrow and rotating service authorization
- Category: Yield
- Definition: A staking pool design rotates a designated maintenance actor based on time-weighted stake and exposes delegation and penalty handling for service participation.

### Matched historical semantic: Peg Recovery Liquidity Buffer
- Match strength: High
- Match evidence: Both describe staking custody with rotating authorization and penalty handling: the extract has time-weighted service stakers, delegation, and slashing/redistribution, while 560 tracks user liquidity, restricted withdrawals for the active role, and guardian/oracle-controlled stake management with penalties.

#### Checklist
- [ ] Check whether: [H-05] `USDMPegRecovery` Risk of fund locked, due to discrepancy between curveLP token value against internal contract math
  - Severity: High
  - Historical root cause: The contract tracks user deposits in fixed internal token balances while its liquidity-provision and withdrawal paths operate on a mutable pool share whose real value changes after swaps. Because the internal ledger is not reconciled against the live pool valuation, the recorded balances drift from the actual claimable amounts and eventually cannot be withdrawn cleanly.
  - Risk pattern: Internal accounting stores separate balances for each deposited asset while liquidity actions use live pool state; pool swaps change the ratio between the assets and the actual claimable share; withdrawal logic assumes the stored balances still correspond to the live position, so the accounting invariants break after price movement or imbalance.
    
    — additional pattern (from raw "[H-01] The design of `wibBTC` is not fully compatible with the current Curve StableSwap pool"): Static pool balance accounting diverges from a rebasing wrapped token whose live balance increases automatically without a pool-side sync primitive.
  - Exploit shape: A user deposits matched amounts of the two assets, the pool experiences at least one swap, and then the user attempts to withdraw the original position. Because the live pool composition has diverged from the stored balances, the withdrawal calculation no longer matches the actual holdings and the transaction can fail or leave value trapped.
    
    — additional exploit (from raw "[H-01] The design of `wibBTC` is not fully compatible with the current Curve StableSwap pool"): A user adds liquidity when the rebasing share price is 1, the wrapped token appreciates over time, and on withdrawal the pool returns only the stale recorded amount instead of the higher live balance.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Keeper and liquidity-provider inflation gauges
- Match strength: High
- Match evidence: Both describe stake-based rewards with delegated/authorized participation and penalty handling; the extract’s rotating maintenance actor and delinquency penalties closely match the keeper/gauge model of eligible stakers plus punishment via stake reduction.

#### Checklist
- [ ] Check whether: [H-04] Deleting `nft Info` can cause users’ `nft.unpaidRewards` to be permanently erased
  - Severity: High
  - Historical root cause: The withdrawal flow deletes the entire per-NFT accounting record after the reward payout attempt, but that record is also the sole durable store for unpaid reward carryover. If the payout helper records a shortfall because the reward balance is insufficient, the subsequent deletion erases the shortfall state before it can be claimed later.
  - Risk pattern: The withdrawal sequence calls the reward-sending helper first, then deletes the NFT accounting struct, and only afterward returns the NFT and updates aggregate staking totals. The unpaid reward field lives inside the deleted struct, so any partially accrued balance stored there is lost once deletion occurs.
  - Exploit shape: (1) A staker withdraws while the reward pool balance is smaller than the accrued reward amount, (2) the reward helper stores the unpaid remainder in the NFT accounting record, (3) withdraw continues and deletes that record, (4) the NFT is returned to the user, and (5) the unpaid rewards are permanently unrecoverable because the carryover state has been erased.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Vested Token Claim Withdrawal and Schedule Revocation
- Match strength: High
- Match evidence: Both describe escrowed stake with delayed withdrawal and penalty/revocation mechanics; the extract adds rotating service authorization and delinquency penalties, while 339 covers vesting-escrow withdrawal and administrator revocation of unvested liability.

#### Checklist
- [ ] Check whether: [H-01] Loss of vested amounts
  - Severity: High
  - Historical root cause: The revocation path zeroes out a user's active entitlement without first preserving the amount that had already vested but had not yet been withdrawn. The accounting state for withdrawn tokens is not separated from the vesting-rights state, so a revocation can extinguish previously earned balance instead of only stopping future accrual.
  - Risk pattern: A claim is marked inactive during revocation and the active-claim check is then used by withdrawal logic to block access. The state does not retain a separate deactivation timestamp or equivalent vesting cutoff, and revocation reduces reserved allocation based on the full claim rather than preserving already-vested-but-unwithdrawn amounts. Withdrawal and revocation are order-dependent against the same claim state.
    
    — additional pattern (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): Claim bookkeeping uses the transfer destination as the claimed key instead of caller identity; the withdrawal path lacks a caller-based one-time-claim check; repeated calls can reuse the same entitlement against a shrinking shared reserve.
  - Exploit shape: (admin, revoke path, claim with partially vested balance, before the beneficiary withdraws) => the claim becomes inactive and later withdrawal reverts, permanently preventing collection of the vested portion. If the beneficiary withdraws first, the vested portion is paid; if the admin revokes first, the same vested portion is lost. The attacker is the privileged administrator or any entity able to call the revocation path on behalf of the beneficiary.
    
    — additional exploit (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): A participant can withdraw once to one address, then withdraw again to a different address because the claimed flag follows the destination, not the principal who is draining the pool.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Permanent freeze of vested tokens due to overflow in `_baseVestedAmount`
  - Severity: High
  - Historical root cause: The linear vesting calculation multiplies a large vested-amount field by an elapsed-time field using a type that is too narrow for the intermediate product. When the product exceeds the maximum representable value, the computation reverts, preventing the vesting function from completing.
  - Risk pattern: The vesting math computes an intermediate product from the linear allocation and elapsed duration before dividing by total duration, while the operands are stored in narrow unsigned integer types. The same calculation is used by the vested-balance query that downstream withdrawal depends on, so any overflow in the view/accounting path freezes claims for affected schedules.
  - Exploit shape: A project admin creates a vesting claim with a sufficiently large linear allocation and a long duration. As time advances, a beneficiary calls the claimable-balance or withdrawal flow near the end of vesting; the intermediate multiplication overflows and the transaction reverts. The user cannot recover the tokens through the normal claim path, leaving the allocation effectively frozen until the schedule is manually altered or revoked.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Challenge-Escrowed Assertion and Edge Staking
- Match strength: High
- Match evidence: Both describe a stake-escrow pool with per-holder balances, delegated/authorized maintenance actors, withdrawal restrictions for the active service staker, and penalty-driven stake reduction for delinquent actors.

#### Checklist
- [ ] Check whether: [H-01] Adversary can make honest parties unable to retrieve their assertion stakes if the required amount is decreased
  - Severity: High
  - Historical root cause: The staking and withdrawal logic lets a staker reuse an old, higher-stake branch while treating themselves as inactive once they have any child or their latest staked assertion equals the latest confirmed one. When the required stake is later lowered, a malicious validator can keep an earlier branch alive on the old higher requirement, create a new child through a different participant on the cheaper requirement, and then exit via the inactivity check even though the system still needs the higher locked amount to honor refunds for the older branch. This breaks the accounting link between the stake amount locked on an assertion branch and the amount required for later withdrawals and loser-stake routing.
  - Risk pattern: A stake requirement variable is updated downward while existing assertion branches retain the previous higher requirement; loser-stake escrow transfers still use the older per-assertion required stake; child creation only checks that the caller's current deposited amount meets the parent assertion's required stake; inactivity is defined by either latest confirmed status or existence of any child, rather than confirmation of the full descendant chain; withdrawal/reduce-deposit is allowed once the caller is deemed inactive even if the branch contains stale higher-stake obligations.
  - Exploit shape: 1) A validator creates an assertion under the old high requirement and later has it become a branch with a child. 2) Governance lowers the required stake. 3) The attacker arranges for a new descendant or sibling stake action to be created under the lower amount, potentially through another participant. 4) The attacker calls the withdrawal path once the last staked assertion has a child, satisfying the inactivity check. 5) The shared pool now holds only the lower amount, so honest validators who staked under the original higher requirement cannot fully withdraw their expected stake.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Edge from dishonest challenge edge tree can inherit timer from honest tree allowing confirmation of incorrect assertion
  - Severity: High
  - Historical root cause: Timer inheritance validates only a local edge-link relation and the next-level constraint, but does not distinguish between rival edges that belong to different challenge trees and different assertion branches. As a result, an edge in a dishonest tree can inherit the accumulated unrivalled time of a matching edge in the honest tree, and confirmation logic that depends on timer thresholds can then be triggered on the wrong branch. The bug is caused by permitting timer state to propagate across equivalent rival edges without binding the inherited timer to the exact lineage of the inheriting edge.
  - Risk pattern: Timer cache update uses an inheritance path that checks only edge origin identity and immediate level progression; rival edges with the same mutual identity are treated as eligible inheritors; timer accumulation is stored per edge and later consumed by confirmation logic; confirmation can be triggered once unrivalled time crosses a threshold, without revalidating that the timer originated from the same challenge tree lineage.
  - Exploit shape: 1) An honest edge in one challenge tree accumulates unrivalled time. 2) A malicious participant identifies a rival edge in a different tree with the same mutual identity and invokes the timer inheritance path using the honest edge as the claimed source. 3) The rival edge's timer cache is boosted to match the honest timer progress. 4) The attacker propagates that time upward through the dishonest tree by updating children timers. 5) Once the dishonest root edge reaches the required time threshold, the attacker front-runs confirmation and gets an incorrect assertion confirmed.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Shared Vault Deposit, Withdrawal, Share Transfer, and Flash Loan
- Match strength: High
- Match evidence: Both describe a shared staking/vault custody model with per-holder balances, withdrawals from shared custody, delegation/authorization of service actors, and penalty handling for delinquent participation.

#### Checklist
- [ ] Check whether: [H-03] `erc721DecreaseIsolateSupplyOnLiquidate()` missing clear `lockerAddr`
  - Severity: High
  - Historical root cause: The isolated-collateral liquidation path clears ownership and supply mode but leaves the lock marker unchanged. Later withdrawal validation checks the lock marker, so stale locker state survives across a round-trip from isolated liquidation to normal deposit and permanently blocks withdrawal.
  - Risk pattern: Liquidation resets owner and supply mode but not the lock field; deposit does not overwrite the lock field on re-entry; withdrawal requires the lock field to be zero; the same stale lock also blocks other isolated flows that depend on an unlocked token state.
    
    — additional pattern (from raw "[H-02] `VoteEscrowDelegation._writeCheckpoint` fails when `nCheckpoints` is 0"): Checkpoint update logic still indexes `nCheckpoints - 1` without guarding the empty-history case, so the first delegation cannot create initial state.
    
    — additional pattern (from raw "[H-11] Cannot remove delegation from a token to another token"): Removal routine indexes checkpoint data by the wrong token ID; the true delegatee entry remains in its checkpoint history and continues counting delegated power.
    
    — additional pattern (from raw "[H-04] Old delegatee not deleted when delegating to new tokenId"): Delegation mapping is overwritten without pruning the prior delegatee’s membership list before writing the next checkpoint.
    
    — additional pattern (from raw "[H-10] Upon changing of delegate, `VoteDelegation` updates both the previous and the current checkpoint"): The update path loads the latest delegated-token array by storage, mutates it, and then forwards the same storage-backed array into the checkpoint writer, allowing history to be corrupted across checkpoints.
    
    — additional pattern (from raw "[H-07] `_writeCheckpoint` does not write to storage on same block"): Same-block branch reads the last checkpoint into a memory struct and mutates it, so the updated delegated-token list is not persisted back to storage.
    
    — additional pattern (from raw "[H-06] NFT transferring won’t work because of the external call to `removeDelegation`."): The internal transfer path uses an external self-call to clear delegation state before moving the token; the delegated-state cleanup function requires the sender to be the token owner, but the sender becomes the contract during the external hop.
    
    — additional pattern (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): The burn path overwrites the pending decision struct with default values; the withdrawal check relies on the unlock timestamp inside that struct; the code does not isolate one burned lock from later locks for the same participant in a way that preserves ownership separation.
    
    — additional pattern (from raw "[H-10] Changing NFT contract in the `MochiEngine` would break the protocol"): A mutable engine-level address is read by vaults for ownership checks and position lookups, and the address can be replaced by an operator after live positions already exist. No migration of existing position state accompanies the change.
  - Exploit shape: A user’s isolated NFT is liquidated, which clears ownership but leaves the locker address set. The same user then deposits the NFT again into the vault in a different mode. On withdrawal, the validator sees a nonzero locker address and reverts, trapping the NFT in the system.
    
    — additional exploit (from raw "[H-02] `VoteEscrowDelegation._writeCheckpoint` fails when `nCheckpoints` is 0"): A holder attempts a first delegation to a target with zero checkpoints; the checkpoint read underflows and the delegation transaction reverts before any state can be created.
    
    — additional exploit (from raw "[H-11] Cannot remove delegation from a token to another token"): A holder delegates to another token and later revokes, but the removal path edits the delegator-side history only, so the delegatee keeps the voting weight indefinitely.
    
    — additional exploit (from raw "[H-04] Old delegatee not deleted when delegating to new tokenId"): A user repeatedly delegates one token to different targets; each new target receives weight while the old targets still retain the token in their checkpoint history, inflating governance power.
    
    — additional exploit (from raw "[H-10] Upon changing of delegate, `VoteDelegation` updates both the previous and the current checkpoint"): A user changes delegation in a block where a checkpoint already exists; the old checkpoint is mutated and the new checkpoint is written from the same array, so both historical entries reflect the latest state.
    
    — additional exploit (from raw "[H-07] `_writeCheckpoint` does not write to storage on same block"): A holder delegates once and then re-delegates within the same block; the second update enters the overwrite branch, mutates only a memory copy, and exits without updating stored checkpoint history.
    
    — additional exploit (from raw "[H-06] NFT transferring won’t work because of the external call to `removeDelegation`."): A holder attempts to transfer a delegated voting NFT; the transfer logic calls back into the contract to remove delegation, the ownership check sees the contract rather than the holder, and the transfer reverts.
    
    — additional exploit (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): An attacker creates a malicious pending lock and has it burned. Another user later creates a fresh pending lock. Because the attacker’s record was reset rather than removed, the attacker’s withdrawal call passes the unlock-time check and pulls the later user’s locked assets.
    
    — additional exploit (from raw "[H-10] Changing NFT contract in the `MochiEngine` would break the protocol"): The operator changes the engine's NFT reference after users have opened positions. Subsequent withdraw, repay, or liquidation flows compare against the wrong ownership source, causing legitimate users to lose access to their positions and breaking the protocol's core lifecycle.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] Users cannot unstake from YiedlETHStakingEtherfi.sol, because YieldAccount.sol is incompatible with ether.fi’s WithdrawRequestNFT.sol
  - Severity: High
  - Historical root cause: The unstake flow assumes the per-user yield account can receive an ERC721 minted by the external withdrawal-request system, but that account contract does not implement the required receiver callback. The external mint therefore fails and the withdrawal path cannot complete.
  - Risk pattern: Unstake flow makes an external withdrawal-request call that safe-mints an NFT to a per-user account; the per-user account lacks ERC721 receiver support; the external call failure bubbles up and reverts the full unstake; test coverage passed only because the mock used an unsafe mint path.
    
    — additional pattern (from raw "[H-06] `WstEth` derivative assumes a `~1=1` peg of stETH to ETH"): Withdrawal sets minOut by applying slippage to wrapped-asset amount without checking live exchange rate; user exits and owner rebalancing both depend on that swap succeeding.
    
    — additional pattern (from raw "[H-03] Users can fail to unstake and lose their deserved ETH because malfunctioning or untrusted derivative cannot be removed"): Unstake performs external withdraws for each enabled derivative in sequence; there is no try/catch or skip logic; an admin can zero weight but cannot remove a broken adapter from the loop.
  - Exploit shape: A user stakes into the yield strategy and later calls unstake. The protocol forwards the withdrawal request to the external pool, which safe-mints a request NFT to the user’s yield account. Because the account cannot receive ERC721s safely, the mint fails and the unstake transaction reverts, leaving the position stuck.
    
    — additional exploit (from raw "[H-06] `WstEth` derivative assumes a `~1=1` peg of stETH to ETH"): When the wrapped staking receipt trades below the tolerated band, unstake and rebalance attempts revert because the minimum output is too high for the current exchange rate.
    
    — additional exploit (from raw "[H-03] Users can fail to unstake and lose their deserved ETH because malfunctioning or untrusted derivative cannot be removed"): If one adapter's downstream withdraw/unwind path starts reverting, any unstake or rebalance call that reaches it reverts, preventing users from exiting until the adapter is fixed or removed.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] Referrer can drain `ReferralFeePoolV0`
  - Severity: High
  - Historical root cause: The reward claim path transfers value but never zeroes the caller's accrued reward balance or deducts it from the pool total. That leaves the same claimable amount intact after each withdrawal, so the same account can repeatedly extract the same funds.
  - Risk pattern: Claim logic reads the caller's reward amount and performs a conversion/payout, but does not write back a zero balance or reduce the aggregate rewards counter afterward.
  - Exploit shape: The referrer accrues a reward once, then submits repeated claim transactions from the same address. Each call sees the same stored reward amount and pays it out again, steadily emptying the fee pool.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Time-weighted yield scheduling for variable-duration lending
- Category: Lending
- Definition: A lending engine updates interest rates and borrower accrual indices from supply-demand signals using time-based smoothing and capped floating-point rates.

### Matched historical semantic: Term Lending Offer Book
- Match strength: High
- Match evidence: Both are lending-rate scheduling mechanisms driven by utilization and time-based updates. The extract updates yield using elapsed time, utilization, and smoothed activity with caps, matching the historical term-lending offer book’s rate curves and rate-derived matching logic.

#### Checklist
- [ ] Check whether: [H-01] When `sellCreditMarket()` is called to sell credit for a specific cash amount, the protocol might receive a lower swapping fee than expected
  - Severity: High
  - Historical root cause: A fee formula implementation mismatch exists between the state transition that solves for required debt input and the state transition that credits the fee recipient. The protocol grosses up the trade amount as if fees are charged on a net-of-fee basis, but then records fees using a different base, so accounting under-collects fees on this execution branch.
  - Risk pattern: In the exact-cash-output branch, the code derives debtAmountIn with a gross-up formula using `(PERCENT - swapFeePercent)` in the denominator, but computes `fees` separately as a simple percentage of `cashAmountOut` plus any fragmentation fee. The fee transfer and accounting consume this understated `fees` value.
    
    — additional pattern (from raw "[H-06] RubiconRouter _swap does not pass whole amount to RubiconMarket"): Pre-forward amount is adjusted by subtracting `amount * feeBPS / 10000` instead of solving for the gross amount needed after downstream fee extraction; downstream market fee is applied again on the already-discounted amount; residual dust remains outside the intended swap path.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): User-controlled source address is passed directly into token transfer calls; the recipient of the minted LP tokens is also user-controlled; no access control ties the approval to the caller; approved balances are treated as if they were the caller’s funds.
    
    — additional pattern (from raw "[H-15] `VaderRouter._swap` performs wrong swap"): A three-hop path calls the intermediate swap with swapped positional arguments; the first hop uses the wrong asset-side amount; the pool enforces a native-side balance check that the call cannot satisfy; the final hop is never reached.
    
    — additional pattern (from raw "[H-16] `VaderRouter.calculateOutGivenIn` calculates wrong swap"): The output calculator swaps the first and second pool order; the reserve arguments passed into the swap formula do not match the asset flow; the resulting quote is used as the basis for routing decisions.
  - Exploit shape: A trader submits a market sell order in the mode that targets an exact cash amount out rather than an exact debt amount in. By choosing that execution path, the trader receives the same target cash while the protocol books a smaller fee than intended. Repeating this path across trades systematically reduces fee payments relative to the intended schedule.
    
    — additional exploit (from raw "[H-06] RubiconRouter _swap does not pass whole amount to RubiconMarket"): A user routes a multi-leg swap and the router forwards too little to the market, so part of the caller’s intended input is left unforwarded or stranded as dust.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): The attacker finds an account that has approved the pool, submits a mint with that account as the source, and sets themselves as the LP recipient. The pool transfers the victim’s tokens and credits the resulting liquidity position to the attacker, stealing the entire approved balance.
    
    — additional exploit (from raw "[H-15] `VaderRouter._swap` performs wrong swap"): A user submits any three-hop swap. The router constructs the intermediate call with the wrong amount slot, the first pool rejects the trade due to reserve-side validation, and the transaction reverts. The failure is deterministic for the affected path length.
    
    — additional exploit (from raw "[H-16] `VaderRouter.calculateOutGivenIn` calculates wrong swap"): A caller asks for a three-hop output quote and receives a value that reflects the reverse pool order. If they build a trade using that quote, the execution may revert or settle at a materially different amount than expected.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Collateralized Debt Position Lifecycle
- Match strength: High
- Match evidence: Both are lending-rate engines that accrue interest from utilization/supply-demand signals, maintain borrower indices, and apply capped, time-based rate updates to outstanding positions.

#### Checklist
- [ ] Check whether: [H-01] `V3Vault.sol` permit signature does not check receiving token address is USDC
  - Severity: High
  - Historical root cause: The vault accepts a signed permit payload and forwards it into a token transfer without validating that the signed token permission matches the vault’s actual asset. Because the signed token address is not bound to the asset being credited, a valid permit for any ERC20 can be replayed against the vault’s USDC-accounting path.
  - Risk pattern: Permit-based deposit/liquidation paths decode attacker-supplied permit data, then call the permit transfer helper with the decoded permissions but never assert that the permitted token equals the vault asset. The same unchecked permit flow exists in multiple code paths that accept permit data before transferring value into the vault.
  - Exploit shape: An attacker prepares a signature for an arbitrary ERC20 they control or can source cheaply, then calls the vault’s permit-enabled flow with that payload. Because the token address inside the permit is never compared against the vault asset, the transfer succeeds for the wrong token and the vault credits the attacker as if the correct stablecoin was received, allowing extraction of vault liquidity.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] Owner of a position can prevent liquidation due to the `onERC721Received` callback
  - Severity: High
  - Historical root cause: Liquidation cleanup tries to push the position NFT back to the debtor with a safe transfer, and the entire liquidation path depends on the recipient’s callback returning the expected selector. A malicious debtor contract can deliberately reject the NFT, causing the liquidation transaction to revert and blocking enforcement.
  - Risk pattern: The liquidation cleanup path performs a safe NFT transfer to the position owner as part of state teardown. That external call can invoke arbitrary recipient logic, and the liquidation flow does not have an alternate escape hatch if the recipient reverts or returns an unexpected value.
    
    — additional pattern (from raw "[H-07] Proposer can `start` a perpetual buyout which can only `end` if the auction succeeds and is not rejected"): end() performs an external payout to the proposer before the buyout record is fully reset; start() only checks for inactive state, so a callback can reenter and create a new live auction during finalization; no reentrancy guard or state pre-update prevents the auction from being re-armed.
    
    — additional pattern (from raw "[H-02] Forced buyouts can be performed by malicious buyers"): Failed-auction cleanup performs an external ERC1155 transfer to the recorded proposer; no escrow or claimable withdrawal is used for return funds; a revert in the recipient transfer aborts finalization and leaves buyout state non-inactive.
  - Exploit shape: A borrower holds the position through a contract whose NFT receipt hook reverts when the vault sends the collateral back during liquidation. Once the position becomes unhealthy, a liquidator attempts repayment, but the forced safe transfer fails and the liquidation reverts, leaving the bad debt in place.
    
    — additional exploit (from raw "[H-07] Proposer can `start` a perpetual buyout which can only `end` if the auction succeeds and is not rejected"): Attacker starts a buyout from a contract with a payable callback, lets the auction fail, and calls end; the payout callback reenters start and immediately creates another live auction, preventing the system from staying inactive long enough for others to replace it.
    
    — additional exploit (from raw "[H-02] Forced buyouts can be performed by malicious buyers"): Attacker creates a buyout from a contract that lacks ERC1155 receive handling, lets the buyout fail, and any call to end reverts while returning tokens to the proposer, so the stale auction remains and no fresh auction can start.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-05] Lenders can escape the blacklisting of their accounts because they can move their MarketTokens to different accounts and gain the `WithdrawOnly` Role on any account they want
  - Severity: High
  - Historical root cause: An authorization-update entrypoint is callable by anyone and forwards a boolean derived from whether an address is present in the controller's authorized-lender set. For any unregistered address, that boolean is false, and the market converts false into a `WithdrawOnly` approval, letting arbitrary callers mint a usable withdrawal role on fresh accounts.
  - Risk pattern: Public controller-level authorization updates iterate over markets and call the market's account-authorization setter with a boolean derived from whitelist membership. The market interprets false as withdrawal-only approval rather than denial, so any non-whitelisted address becomes eligible to queue and execute withdrawals if it holds market tokens.
    
    — additional pattern (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): Claim bookkeeping uses the transfer destination as the claimed key instead of caller identity; the withdrawal path lacks a caller-based one-time-claim check; repeated calls can reuse the same entitlement against a shrinking shared reserve.
    
    — additional pattern (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): The resume function checks only per-pool pause state; it does not inspect the caller or require an owner/operator role; it flips the shared locked flag to false once checks pass.
  - Exploit shape: A lender learns their original address is sanctioned, transfers their market tokens to new addresses they control, then calls the public authorization-update function on those recipient addresses. Each recipient is marked withdrawal-only, allowing the lender to queue withdrawals from the fresh accounts and exit despite the blacklist.
    
    — additional exploit (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): A participant can withdraw once to one address, then withdraw again to a different address because the claimed flag follows the destination, not the principal who is draining the pool.
    
    — additional exploit (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): An LP waits until the external pool states satisfy the pause check, calls resume from their own account, and clears the shared lock before compensation accounting is finalized.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Piecewise Interest Curve Evaluation
- Match strength: High
- Match evidence: Both center on utilization- and time-driven interest/yield curves with capped rate updates and borrower accrual indices used to update lending accruals.

#### Checklist
- [ ] Check whether: [H-01] Incorrect `blocksPerYear` constant in `WhitepaperInterestRateModel`
  - Severity: High
  - Historical root cause: A per-block interest formula converts annual rates by dividing by a hardcoded blocks-per-year constant that does not match the chain's actual block cadence. Because the denominator is too small, every annual rate parameter is scaled into an oversized per-block rate, permanently distorting borrow and supply accrual math.
  - Risk pattern: A fixed annual-to-block conversion constant is used in rate initialization and interest accrual math, but the deployed chain's real blocks-per-year value is materially different. The per-block base rate and per-block multiplier are both derived from that constant, so every downstream borrow-rate and supply-rate computation inherits the same scaling error.
  - Exploit shape: An attacker does not need to manipulate state directly; they can simply interact with the affected market after deployment. Once a market is configured with the bad conversion constant, borrowers accrue at the inflated rate and suppliers observe the mismatched yield curve. Arbitrage and normal market activity cannot restore the intended curve because the protocol's own rate parameters are mis-scaled from the start.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Bucketed fixed-term bond issuance and redemption
- Category: Lending
- Definition: A fixed-maturity lending product mints maturity-specific bond records, tracks per-bucket supply-demand, and settles redemption with fallback issuance when liquidity is insufficient.

### Matched historical semantic: Collateralized Debt Position Lifecycle
- Match strength: High
- Match evidence: Both track maturity/bucketed lending positions with borrower records, aggregate lending totals, and redemption/withdrawal paths that handle liquidity shortfalls or fallback settlement behavior.

#### Checklist
- [ ] Check whether: [H-01] Mismatch between yield amount deposited in shares calculation and `getAccountYieldBalance()`
  - Severity: High
  - Historical root cause: A yield adapter records the returned share amount from an external deposit as if it were the deposited asset amount, but later computes per-account yield from the underlying asset balance. Because the adapter mints fewer shares than assets when the share price has appreciated, the stored stake accounting and the balance-based yield accounting diverge on every deposit.
  - Risk pattern: Deposit flow stores the integration return value in stake accounting; later read paths derive yield from total underlying balance; share-to-asset conversion is not normalized to the same unit in both places; repeated deposits into one shared yield account accumulate drift between per-NFT debt and per-NFT yield.
    
    — additional pattern (from raw "[H-02] wrong minting amount"): A mint amount variable is derived from `baseBalance * ONE / redeemRate` instead of the transfer delta; the result depends on the contract’s live balance before/after the call rather than on the user’s deposit amount; downstream issuance uses that computed value as the minted supply.
    
    — additional pattern (from raw "[H-05] Oracle returns an improperly scaled USDV/VADER price"): The pricing routine multiplies and divides fixed-point quantities but never normalizes the final result to the system's expected 18-decimal convention; downstream mint/burn code consumes the raw return value as if it were normalized.
    
    — additional pattern (from raw "[H-03] Oracle doesn’t calculate USDV/VADER price correctly"): The oracle averages per-pair contributions expressed in different units before converting them to a common denomination, producing a mathematically invalid exchange rate that downstream code trusts.
    
    — additional pattern (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): User-controlled source address is passed directly into token transfer calls; the recipient of the minted LP tokens is also user-controlled; no access control ties the approval to the caller; approved balances are treated as if they were the caller’s funds.
    
    — additional pattern (from raw "[H-03] VADER contains a Fee-On-Transfer"): Deposit logic uses the requested amount instead of measuring pre/post balances; withdrawal logic trusts the recorded share balance; repeated enter/leave cycles compound the accounting gap created by transfer fees.
    
    — additional pattern (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The mint function trusts user-controlled `from` and `to` parameters; token transfer uses the provided source address rather than binding to the caller; minted output is sent to an arbitrary recipient; there is no authorization check tying the source to the spender.
    
    — additional pattern (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): Caller controls the source account used for both token transfers; caller controls the recipient of minted LP tokens; the function lacks a spender-owner relationship check; the output position is minted based solely on supplied parameters.
    
    — additional pattern (from raw "[H-21] Lack of access control allow attacker to `mintFungible()` and `mintSynth()` with other user’s wallet balance"): The source address for token pulls is caller-controlled; the destination address for minted output is caller-controlled; no authorization check ensures the source equals the caller or a delegated operator; approvals on the token side are sufficient to trigger the theft.
    
    — additional pattern (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): Deposit share minting is based on the raw amount of the input asset, and share redemption converts shares back into any requested output asset using the same nominal-unit balance model. No oracle or relative-price adjustment is applied across the accepted asset set.
    
    — additional pattern (from raw "[H-06] earn results in decreasing share price"): Vault-level balance aggregation sums normalized token balances from the vault itself, while controller-level balance aggregation adds only the strategy's want-side balance without applying a common price conversion. The earn path updates strategy balances using those mismatched units, so total value accounting becomes inconsistent across components.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
    
    — additional pattern (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): The balance aggregator normalizes on-hand token balances but directly adds the controller-reported strategy balance without scaling it to the same precision. Any consumer of the total-balance view then inherits the mixed-unit result.
  - Exploit shape: An attacker stakes one collateral position, then stakes a second position into the same yield account after the external pool has a non-1:1 asset/share rate. The first position is credited with more apparent yield than it should have, while the second position is credited with less. The attacker then withdraws or claims against the inflated position, leaving the other position undercollateralized and closer to liquidation.
    
    — additional exploit (from raw "[H-02] wrong minting amount"): An attacker chooses a deposit timing when the contract base balance is favorable. They call the minting path with a small or manipulated deposit. Because the calculation keys off the existing balance, the attacker receives an inflated or deflated mint amount relative to the actual deposit, extracting value from the pool of token holders.
    
    — additional exploit (from raw "[H-05] Oracle returns an improperly scaled USDV/VADER price"): A caller queries the feed for a normal pair and receives a mis-scaled price, causing mint, burn, or reimbursement code to overpay or undercharge by the scaling factor.
    
    — additional exploit (from raw "[H-03] Oracle doesn’t calculate USDV/VADER price correctly"): Multiple pairs feed the oracle; their contributions are combined before normalization; downstream mint/burn and reimbursement code consumes the wrong aggregate price.
    
    — additional exploit (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): The attacker finds an account that has approved the pool, submits a mint with that account as the source, and sets themselves as the LP recipient. The pool transfers the victim’s tokens and credits the resulting liquidity position to the attacker, stealing the entire approved balance.
    
    — additional exploit (from raw "[H-03] VADER contains a Fee-On-Transfer"): An attacker deposits a fee-on-transfer token, receives credit for the full nominal amount, then withdraws. The contract returns value based on the inflated credit even though it never received the full deposit. Repeating the cycle extracts the fee difference and can drain the wrapper over time.
    
    — additional exploit (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The attacker monitors approvals, then submits a mint transaction that names the victim as the source and the attacker as the recipient. The pool transfers the victim’s approved tokens, mints the synthetic asset, and sends the output to the attacker before the victim can react.
    
    — additional exploit (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): The attacker watches for token approvals to the pool, then submits a liquidity mint with the victim as source and the attacker as recipient. The contract transfers the victim’s assets, mints LP units, and assigns them to the attacker, stealing the victim’s approved balance.
    
    — additional exploit (from raw "[H-21] Lack of access control allow attacker to `mintFungible()` and `mintSynth()` with other user’s wallet balance"): The attacker scans for wallets with standing approvals, then invokes the minting helper with the victim as the source and themselves as the recipient. The pool transfers the victim’s assets and mints either LP tokens or synthetic claims to the attacker, draining the victim’s approved balance.
    
    — additional exploit (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): An attacker deposits a high-priced allowed asset while the vault's accounting credits them as if it were equal to a lower-priced asset. They then redeem their shares for the lower-priced asset or another asset in the basket. The difference between the deposit asset's real value and the withdrawal asset's real value becomes attacker profit and comes out of the pool.
    
    — additional exploit (from raw "[H-06] earn results in decreasing share price"): A user deposits the base asset into the vault and waits for yield realization. Another actor triggers the earn path, which moves funds into the strategy and updates accounting in a different unit than the vault uses for its total-value calculation. After the call, the reported share price is lower than before, so all holders can redeem for less than their prior claim.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
    
    — additional exploit (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): An attacker chooses a vault configuration where the strategy-side asset uses fewer decimals than the vault's internal normalization. They deposit into the vault and observe that the total balance is understated relative to reality, then use that distorted figure to receive an unfair share allocation or to redeem for an amount that does not match the true asset value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-08] The bot won’t be able to unstake or repay risky positions in the yield contract
  - Severity: High
  - Historical root cause: The emergency-closeout paths look up the borrower’s yield account using the transaction sender rather than the target position owner. When the privileged bot executes the action, it resolves to the bot’s own account, which is wrong or absent, so the forced close operation cannot target the risky position.
  - Risk pattern: Forced unstake and repay paths derive the yield-account address from caller context; the borrower/user address is not supplied to those internal flows; the privileged bot is expected to act for others; failure occurs before the protocol can unwind the unhealthy position.
    
    — additional pattern (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): The burn path overwrites the pending decision struct with default values; the withdrawal check relies on the unlock timestamp inside that struct; the code does not isolate one burned lock from later locks for the same participant in a way that preserves ownership separation.
    
    — additional pattern (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): User-controlled source address is passed directly into token transfer calls; the recipient of the minted LP tokens is also user-controlled; no access control ties the approval to the caller; approved balances are treated as if they were the caller’s funds.
    
    — additional pattern (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The mint function trusts user-controlled `from` and `to` parameters; token transfer uses the provided source address rather than binding to the caller; minted output is sent to an arbitrary recipient; there is no authorization check tying the source to the spender.
    
    — additional pattern (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): Caller controls the source account used for both token transfers; caller controls the recipient of minted LP tokens; the function lacks a spender-owner relationship check; the output position is minted based solely on supplied parameters.
    
    — additional pattern (from raw "[H-21] Lack of access control allow attacker to `mintFungible()` and `mintSynth()` with other user’s wallet balance"): The source address for token pulls is caller-controlled; the destination address for minted output is caller-controlled; no authorization check ensures the source equals the caller or a delegated operator; approvals on the token side are sufficient to trigger the theft.
  - Exploit shape: A position becomes risky and the bot attempts to unstake or repay it. Because the code resolves the yield account from the bot’s address, it gets the wrong account and the call reverts. The unhealthy position remains open and continues accruing risk.
    
    — additional exploit (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): An attacker creates a malicious pending lock and has it burned. Another user later creates a fresh pending lock. Because the attacker’s record was reset rather than removed, the attacker’s withdrawal call passes the unlock-time check and pulls the later user’s locked assets.
    
    — additional exploit (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): The attacker finds an account that has approved the pool, submits a mint with that account as the source, and sets themselves as the LP recipient. The pool transfers the victim’s tokens and credits the resulting liquidity position to the attacker, stealing the entire approved balance.
    
    — additional exploit (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The attacker monitors approvals, then submits a mint transaction that names the victim as the source and the attacker as the recipient. The pool transfers the victim’s approved tokens, mints the synthetic asset, and sends the output to the attacker before the victim can react.
    
    — additional exploit (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): The attacker watches for token approvals to the pool, then submits a liquidity mint with the victim as source and the attacker as recipient. The contract transfers the victim’s assets, mints LP units, and assigns them to the attacker, stealing the victim’s approved balance.
    
    — additional exploit (from raw "[H-21] Lack of access control allow attacker to `mintFungible()` and `mintSynth()` with other user’s wallet balance"): The attacker scans for wallets with standing approvals, then invokes the minting helper with the victim as the source and themselves as the recipient. The pool transfers the victim’s assets and mints either LP tokens or synthetic claims to the attacker, draining the victim’s approved balance.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Risk of reentrancy `onERC721Received` function to manipulate collateral token configs shares
  - Severity: High
  - Historical root cause: During collateral token replacement, the receiver callback performs an internal accounting cleanup that sends the old position back out before the new-position collateral totals are finalized. That call ordering lets the recipient reenter mid-transition and run debt-changing logic against the same loan state, so the total-debt-share accounting is applied twice against a mutated intermediate state.
  - Risk pattern: The receiver hook copies debt to a new token, calls the old-loan cleanup routine, and only later updates collateral accounting for the new token. The cleanup routine itself transfers the old NFT back to the owner, which reenters the receiver hook on the owner side. Because debt-share totals are updated before and after the callback, the same loan transition can be accounted twice against modified loan state.
  - Exploit shape: A borrower initiates a transformation that triggers receipt of a new collateral NFT. When the vault sends the old NFT back, the borrower’s receiver hook reenters and calls a debt-changing function on the replacement position. When control returns, the vault applies its post-cleanup collateral update again using the already-mutated debt shares, permanently inflating the underlying pair’s total-debt-share counters and blocking future borrowing.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Maturity-Bound Principal Token Redemption
- Match strength: High
- Match evidence: Both center on fixed-term principal/bond positions with maturity-specific records, redemption logic, and yield-rate snapshots tied to maturity buckets and current exchange rates.

#### Checklist
- [ ] Check whether: [H-01] Mismatch in `withdraw()` between Yearn and other protocols can prevent Users from redeeming zcTokens and permanently lock funds
  - Severity: High
  - Historical root cause: The withdrawal path assumes the numeric withdrawal argument represents underlying assets for every supported yield adapter, but the year-based adapter interprets that argument as shares. As a result, the caller computes a redemption amount in assets, yet the adapter burns shares instead of withdrawing that many assets, breaking the asset/share invariant and causing either premature revert or excess assets to remain trapped in the integration contract.
  - Risk pattern: The redemption logic passes an asset amount into a vault adapter whose withdrawal primitive burns shares. The code does not convert between assets and shares using the live exchange rate before calling the adapter, so the same input is interpreted inconsistently across integrations. The downstream redemption path then assumes the adapter returned exactly the intended asset amount and continues accounting as if no excess or shortfall existed.
    
    — additional pattern (from raw "[H-02] RubiconRouter: Offers created through offerForETH cannot be cancelled"): Native-asset-to-token offer creation stores funds in an order record; the router lacks the matching cancel path for that order class; assets are only recoverable through a missing exit branch rather than a user-controlled withdrawal path.
    
    — additional pattern (from raw "[H-04] Controller does not raise an error when there’s insufficient liquidity"): The withdrawal loop reduces the requested amount across available balance sources and exits even when a nonzero remainder is left. No final check enforces that the full requested amount was delivered before share accounting completes.
    
    — additional pattern (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): The withdrawal routine computes a normalized amount from share value, compares it to a raw token balance, and subtracts the raw balance from the normalized target to derive a controller withdrawal request. The post-withdraw adjustment also mixes raw and normalized quantities.
  - Exploit shape: 1) A user deposits underlying assets into the system, minting receipt tokens. 2) The system later tries to redeem the user's position by forwarding the nominal asset amount to the share-based adapter. 3a) If the adapter has fewer shares than the nominal amount, the withdrawal reverts and the user cannot exit. 3b) If the adapter has enough shares, it burns more shares than needed, returns more assets than the user should receive, and leaves surplus assets in the holding contract. 4) Subsequent withdrawals can fail because the adapter share balance has been depleted, leaving stranded funds.
    
    — additional exploit (from raw "[H-02] RubiconRouter: Offers created through offerForETH cannot be cancelled"): A user opens an offer, it remains unfilled, and because the cancel path is absent the escrowed tokens remain trapped indefinitely.
    
    — additional exploit (from raw "[H-04] Controller does not raise an error when there’s insufficient liquidity"): An attacker watches for a large pending withdrawal. They front-run by withdrawing the liquid portion of the target asset from the vault and strategy, leaving insufficient liquidity. The victim's withdrawal then executes against the depleted pool, burns shares, and returns nothing or less than expected because the function does not revert on the remaining shortfall.
    
    — additional exploit (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): An attacker redeems a small number of shares for a low-decimal output asset. Because the code compares normalized and raw balances, it computes a bogus deficit and asks the controller for an inflated top-up. The attacker then receives an excessive amount of the output asset relative to their shares, draining value from the pool.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Auto-renewing hourly bond subscription accounting
- Category: Lending
- Definition: An hourly bond system accrues principal with a rolling yield accumulator, enforces a limited cancellation window, and periodically refreshes borrow-side and lend-side rate indices.

### Matched historical semantic: Locked Asset Redemption into Yield Receipt
- Match strength: High
- Match evidence: Both manage rolling reward accounting with checkpointing and accrual over time before withdrawal. The extract’s hourly bond accumulator and limited withdrawal window align with the historical receipt/reward staking flows that update accrued rewards and then settle on claim or withdrawal.

#### Checklist
- [ ] Check whether: [H-01] Availability of deposit invariant can be bypassed
  - Severity: High
  - Historical root cause: The accounting step that determines user proceeds after receipt-asset conversion reads the aggregate native-asset balance of the contract, not the swap output amount for the specific claim. Because direct transfers can increase that balance without updating per-user lock accounting, the subsequent mint/stake step over-credits the claimant.
  - Risk pattern: A one-time conversion routine deposits the entire contract native-asset balance into a downstream minter and stores the resulting total claim-share balance as the backing numerator for later proportional claims. Claim redemptions for native-asset deposits use a `totalClaimShares / totalSupply` style ratio. The contract can receive unsolicited native-asset transfers before conversion, and those transfers are not segregated from accounted deposits.
    
    — additional pattern (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): The contract maintains one native-side reserve balance for both synthetic issuance backing and ordinary LP liquidity; LP mint/burn calculations read the same aggregate reserve, so withdrawals can redeem against synth-backed value.
    
    — additional pattern (from raw "[H-29] VaderPoolV2.mintFungible exposes users to unlimited slippage"): LP share output is computed from current reserves; no minimum minted liquidity parameter exists; reserve skew directly changes share issuance; mempool observers can sandwich the mint.
    
    — additional pattern (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): Different liquidity representations coexist without a unified ownership ledger; synth-minted liquidity is not counted when normal LP shares are burned; withdrawal logic can drain all assets even though synth claims remain outstanding.
    
    — additional pattern (from raw "[H-20] Early user can break `addLiquidity`"): When total liquidity is zero, the first mint sets share supply equal to the raw deposit; no initial liquidity is sent to an unrecoverable address; later mints depend on that initial supply for proportional calculations.
  - Exploit shape: An attacker accumulates multiple locked native-asset or wrapped-native-asset positions. Right before the authorized party triggers the global conversion transaction, the attacker front-runs with a direct native-asset donation to the contract. The conversion records a higher total claim-share backing than tracked deposits. The attacker then back-runs with claims across their positions and receives an above-par amount on each redemption because the global ratio now includes the donation.
    
    — additional exploit (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): A synth minter deposits native assets to back a synthetic position; a later LP burn redeems from the merged reserve, consuming the synth-backed portion; the synth minter later receives less native value than originally contributed.
    
    — additional exploit (from raw "[H-29] VaderPoolV2.mintFungible exposes users to unlimited slippage"): The victim submits a large liquidity mint. The attacker front-runs by trading in the direction that devalues the side the victim is overweight in, lets the mint execute at the depressed valuation, and back-runs to restore the original reserves. The victim gets fewer LP units than the deposit should have minted.
    
    — additional exploit (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): A user mints synth exposure, another liquidity provider withdraws the normal LP position that controls the actual pool shares, and the pool is emptied before the synth holder can redeem. The synth holder is left with a claim against an asset pool that no longer contains sufficient backing.
    
    — additional exploit (from raw "[H-20] Early user can break `addLiquidity`"): The attacker becomes the first liquidity provider and deposits only a tiny amount of the native side. That sets a distorted base share supply, after which later providers cannot add liquidity on fair terms because their minted shares are effectively rounded against the attacker’s tiny bootstrap position.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-08] `MasterChef.sol` Users won’t be able to receive the `concur` rewards
  - Severity: High
  - Historical root cause: Reward distribution depends on the live balance of the deposited asset held by the accounting contract, but the actual user deposits are retained elsewhere and never transferred into that balance. The pool supply check therefore always evaluates to zero, causing the reward update routine to short-circuit and permanently suppress reward accrual.
  - Risk pattern: Reward update reads the deposit asset balance from the accounting contract itself; deposits only mutate internal user accounting and do not increase that balance; the zero-supply branch exits before any per-share reward increment is applied, so reward state never advances.
  - Exploit shape: A user stakes through the upstream depositor, then the reward updater runs. Since the accounting contract holds none of the deposit asset, the supply read is zero and the update exits. Repeating deposits and withdrawals never changes this condition, so no user can harvest the intended reward token emissions.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-04] `ConvexStakingWrapper`, `StakingRewards` Wrong implementation will send `concur` rewards to the wrong receiver
  - Severity: High
  - Historical root cause: The deposit/withdraw adapter forwards stake changes through a master accounting layer that keys user positions by the caller, but the adapter calls that layer as the wrapper contract rather than as the end user. As a result, the reward debt and pending reward settlement are attributed to the adapter address, while reward transfers are directed to whichever recipient parameter is passed in, breaking ownership binding.
  - Risk pattern: Adapter stake flows invoke the master accounting layer without a user-identity parameter, so the caller recorded in the master layer is the adapter itself; the reward settlement logic pays out to a separate recipient argument; user balances in the wrapper and balances in the master layer diverge because one layer tracks the adapter while the other tracks end users.
    
    — additional pattern (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): Collateral-send path calls unwrap before reward update; user reward state remains stale at the moment the wrapped collateral is burned/removed; later reward claims can still read the pre-withdrawal balance and pay out yield on exited collateral.
    
    — additional pattern (from raw "[WM-04] ActivePool does not update rewards before unwrapping wrapped asset"): Collateral transfer routine performs unwrap before reward claim/update; wrapper commentary indicates rewards should be updated prior to burn; reward update reads stake and reward debt after the unwrap has already changed the user balance.
  - Exploit shape: Alice deposits through the wrapper. Later Bob performs a small action through the same wrapper, which causes the master layer to settle the adapter’s accumulated rewards and send them to Bob’s chosen recipient parameter. The rewards generated by Alice’s stake are therefore released under the adapter’s entry and can be redirected away from Alice.
    
    — additional exploit (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): A collateral manager unwraps a user’s wrapped position and only later updates rewards; because the reward ledger reads the post-burn state, the user can either lose accrued yield or keep claiming against stale stake, depending on the direction of the accounting error.
    
    — additional exploit (from raw "[WM-04] ActivePool does not update rewards before unwrapping wrapped asset"): A user with wrapped collateral accrues rewards, then the pool sends the collateral out and only afterward updates rewards; the pre-withdrawal entitlement is no longer reflected correctly, so later distribution can misallocate value based on stale state.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Token Vesting Schedule Management
- Match strength: High
- Match evidence: Both center on linear time-based accrual with a rolling accumulator and withdrawal windows; the extract is hourly bond accounting, and 340 is vesting schedule management with cliff/linear release and claim tracking.

#### Checklist
- [ ] Check whether: [H-05] BathToken LPs Unable To Receive Bonus Token Due To Lack Of Wallet Setter Method
  - Severity: High
  - Historical root cause: A critical reward-distribution address is never initialized through any setter or initialization path, leaving the reward-distribution branch permanently disabled. Because the contract depends on a nonzero wallet reference to trigger bonus release, failing to validate and set that configuration input makes the reward flow unreachable.
  - Risk pattern: Reward distribution checks a vesting-wallet state variable before releasing bonus tokens; that state variable has no assignment path after deployment; the zero address remains the default and causes the reward-release branch to skip execution forever.
  - Exploit shape: 1) The system is deployed without setting the reward-wallet address. 2) Users deposit and later withdraw expecting bonus rewards. 3) Withdrawal logic checks the uninitialized address and skips the release call. 4) Bonus tokens remain trapped and LPs never receive them.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] Attacker could steal almost all the bonus tokens in BathBuddy Vesting Wallet
  - Severity: High
  - Historical root cause: Reward release is computed from the caller’s current pool share at withdrawal time, rather than from share ownership over the vesting interval. This makes the payout sensitive to same-block capital inflows: an attacker can temporarily dominate the pool, trigger reward release under the inflated share distribution, and then exit, draining almost all vested rewards from earlier participants.
  - Risk pattern: Reward amount is computed as `releasable * sharesWithdrawn / initialTotalSupply` using the current withdrawal share rather than time-weighted ownership; withdraw triggers bonus release in the same transaction; pool share can be inflated just before the release call and reduced immediately after.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
  - Exploit shape: 1) Attacker acquires large temporary liquidity. 2) Attacker deposits into the pool shortly before a large vesting release is available, obtaining a dominant share. 3) Attacker withdraws in the same transaction or same block, causing the bonus release to use the inflated share fraction. 4) Attacker receives most of the vested bonus tokens and repays the temporary liquidity. 5) Honest LPs later withdraw and receive only dust.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] StakedCitadel: wrong setupVesting function name
  - Severity: High
  - Historical root cause: The withdrawal path calls a vesting entrypoint name that does not exist in the vesting adapter’s interface implementation. As a result, the external call fails during withdrawal, so users cannot complete the exit flow and their funds remain inaccessible through the intended path.
  - Risk pattern: The withdrawal flow makes an external call to the vesting adapter using a mismatched method name, while the vesting adapter exposes a different method name. The rest of the withdrawal path depends on that call succeeding before token transfer and completion.
    
    — additional pattern (from raw "[H-09] `removeToken` would break the vault/protocol."): The manager's token-removal flow updates the token registry without checking that vault-local balances and strategy balances for that asset are zero or migrated. Later balance and share-price code assumes the registry reflects the live asset set.
  - Exploit shape: A user calls withdraw on the vault. The vault reaches the vesting handoff step and attempts to invoke the nonexistent entrypoint on the vesting contract. The external call reverts, so the entire withdrawal transaction reverts. Every user attempting to withdraw experiences the same failure until the call target or interface is corrected.
    
    — additional exploit (from raw "[H-09] `removeToken` would break the vault/protocol."): An authorized operator removes an asset from a vault before migrating its live balance. The vault still holds or has deployed that asset, but the registry no longer tracks it. Subsequent withdrawals and balance queries misprice the vault and can strand the removed asset, preventing users from redeeming the true value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Yield-Bearing Wrapper Mint and Redemption
- Match strength: High
- Match evidence: Both are rolling bond/wrapper accounting systems that snapshot an accumulator, refresh principal on interaction, and use periodic rate updates plus constrained withdrawal windows to preserve redeemability.

#### Checklist
- [ ] Check whether: [H-05] Inflation of ggAVAX share price by first depositor
  - Severity: High
  - Historical root cause: The share price of the vault is initialized by the first deposit and can later be skewed by a donation plus reward-sync sequence, so the exchange rate depends on who races to initialize the vault and when reward accounting is updated. Because deposits mint shares from a live assets-to-supply ratio, an attacker can front-run initialization and manipulate the ratio before honest users deposit.
  - Risk pattern: The vault’s share conversion uses total supply divided by total assets, and when supply is zero the first depositor receives a 1:1 initial mint. Direct asset transfers to the vault increase total assets without minting shares, and reward synchronization updates accounting on a cycle boundary chosen by the caller’s timing. Deposit minting then rounds down, producing zero-share reverts for small deposits once the ratio is inflated.
  - Exploit shape: An attacker front-runs vault creation, makes a minimal initial deposit, transfers a large amount of underlying asset directly into the vault, and calls reward synchronization near a cycle boundary. After the exchange rate rises, honest users deposit at a worse rate; the attacker then withdraws and captures value that came from the later deposits.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-05] `addFee` will stop accumulating fee once `rewardToken` has reached max supply
  - Severity: High
  - Historical root cause: The max-supply guard exits the fee-accumulation routine before it records the incoming trading fee into epoch accounting. Once the emission cap is reached, protocol fees continue arriving but are no longer indexed for later reward distribution, permanently trapping value in the contract.
  - Risk pattern: A supply-cap check appears before the epoch-fee accounting writes. The early return bypasses all updates to trader fee totals, exchange fee totals, and epoch total fee, so fee deposits are accepted operationally but not booked.
    
    — additional pattern (from raw "[H-06] Any fractions deposited into any proposal can be stolen at any time until it is commited"): Migration buyout kickoff uses the module’s total token balance rather than a per-proposal balance; proposal-specific deposits are recorded but not enforced when transferring tokens into the buyout; a separate proposal can inherit the module’s full fraction inventory.
  - Exploit shape: Once token supply is at or above the cap, traders continue executing fills and sending fees. The fee handler exits immediately, epoch counters do not advance for those amounts, and later reward claims cannot access the trapped value.
    
    — additional exploit (from raw "[H-06] Any fractions deposited into any proposal can be stolen at any time until it is commited"): An attacker waits for a victim proposal to accumulate fractions, then starts a different proposal with a trivial target. The buyout-start path sweeps the module’s full fraction holdings into the attacker’s buyout, allowing capture of other users’ deposited fractions.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Yeti token rebase checks the additional token amount incorrectly
  - Severity: High
  - Historical root cause: The rebase logic computes how much balance may be added to the effective supply using the contract’s full token holdings instead of the newly acquired surplus above the already-accounted balance. That lets the rebasing accumulator credit more effective supply than the contract truly gained, so the internal claim supply can drift beyond realizable holdings.
  - Risk pattern: Rebase path uses full token balance in the additional-balance check; effective supply variable is incremented from that unchecked amount; the correct comparison should be against the surplus over the already tracked effective balance, not the raw on-chain balance.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
  - Exploit shape: A user or market condition causes the contract to hold tokens whose current value differs from the last buyback valuation. When anyone triggers rebase, the function reads the raw contract balance, computes an excessive additional amount, and adds it to the effective balance. Later claim/withdraw flows then rely on this inflated accounting and can face a shortfall when real holdings are insufficient.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Reward tranche accounting with intra-day smoothing
- Category: Yield
- Definition: A tranche-based incentive distributor checkpoints claims over time, accrues reward deltas from changing aggregate rates, and applies intra-day gain-loss adjustments before payout.

### Matched historical semantic: Permissionless Merkle-Scaled Token Distribution
- Match strength: High
- Match evidence: Both are tranche-based reward distribution systems that checkpoint accrued value over time and transfer tokens from shared custody to claimants. The extract’s intra-day smoothing and tranche claims align with the historical Merkle-scaled distribution and windowed claim accounting.

#### Checklist
- [ ] Check whether: [H-05] Centralisation RIsk: Owner Of `RoyaltyVault` Can Take All Funds
  - Severity: High
  - Historical root cause: A privileged fee-setting path lets the owner choose an arbitrarily large platform share, and that share is taken before value reaches the downstream split, so the owner can divert the entire inflow and starve other recipients.
  - Risk pattern: A fee parameter used in royalty settlement is owner-controlled and unconstrained on its upper bound. The settlement routine divides incoming value into a platform share and a remainder that would otherwise be forwarded to the split mechanism, and the owner can set the fee so the remainder becomes negligible or zero.
    
    — additional pattern (from raw "[H-01] Tokens can be burned with no access control"): Role gating depends on unset keeper/controller role variables; utilization transfers the vault’s available token balance to the controller destination without validating that destination is nonzero.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
    
    — additional pattern (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): The balance aggregator normalizes on-hand token balances but directly adds the controller-reported strategy balance without scaling it to the same precision. Any consumer of the total-balance view then inherits the mixed-unit result.
  - Exploit shape: The owner calls the fee-setting path and raises the platform share to the maximum practical value. On the next royalty settlement, almost all value is diverted to the platform recipient under the owner's control, leaving little or nothing for the intended split recipients and potentially breaking transfer-time settlement assumptions.
    
    — additional exploit (from raw "[H-01] Tokens can be burned with no access control"): An attacker waits for deployment or upgrade while both role addresses are still zero, calls the utilization entrypoint, and causes the full available balance to be transferred to the zero address.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
    
    — additional exploit (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): An attacker chooses a vault configuration where the strategy-side asset uses fewer decimals than the vault's internal normalization. They deposit into the vault and observe that the total balance is understated relative to reality, then use that distorted figure to receive an unfair share allocation or to redeem for an amount that does not match the true asset value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Splitter: Anyone can call incrementWindow to steal the tokens in the contract
  - Severity: High
  - Historical root cause: A privileged accounting update that increments the per-window balance ledger is gated only by interface-support and self-reported linkage checks on the caller, which any attacker-controlled contract can satisfy, allowing unauthenticated inflation of distributable window balances.
  - Risk pattern: A public window-increment function trusts msg.sender to be a legitimate royalty source if it reports the expected interface and returns the splitter address, then appends royaltyAmount to balanceForWindow and increments currentWindow after only checking the live token balance against the supplied amount.
    
    — additional pattern (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): Claim bookkeeping uses the transfer destination as the claimed key instead of caller identity; the withdrawal path lacks a caller-based one-time-claim check; repeated calls can reuse the same entitlement against a shrinking shared reserve.
    
    — additional pattern (from raw "[H-06] Referrer can drain `ReferralFeePoolV0`"): Claim logic reads the caller's reward amount and performs a conversion/payout, but does not write back a zero balance or reduce the aggregate rewards counter afterward.
  - Exploit shape: The attacker deploys a contract that advertises the expected interface and returns the victim splitter address from its linkage check, then calls the increment path with a tiny amount and transfers just enough tokens to satisfy the balance check. This pushes currentWindow forward and inflates balanceForWindow; afterward the attacker uses the claim path to extract value based on the corrupted window ledger.
    
    — additional exploit (from raw "[H-03] Repeated Calls to Shelter.withdraw Can Drain All Funds in Shelter"): A participant can withdraw once to one address, then withdraw again to a different address because the claimed flag follows the destination, not the principal who is draining the pool.
    
    — additional exploit (from raw "[H-06] Referrer can drain `ReferralFeePoolV0`"): The referrer accrues a reward once, then submits repeated claim transactions from the same address. Each call sees the same stored reward amount and pays it out again, steadily emptying the fee pool.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] DoS: `claimForAllWindows()` May Be Made Unusable By An Attacker
  - Severity: High
  - Historical root cause: A claim routine iterates over every historical window from zero to a monotonically increasing counter, so unbounded growth of that counter eventually makes the claim exceed block gas limits and prevents completion.
  - Risk pattern: The claim-all logic performs a linear loop from i = 0 to currentWindow and checks/marks each window in turn. currentWindow only increases and can be driven upward over time by repeated legitimate increments or by adversarial calls that advance the window counter.
  - Exploit shape: An attacker repeatedly advances the window counter, either organically through many small deposits or by exploiting the window-increment entrypoint with minimal value. Once currentWindow is large enough, any user attempting the all-windows claim hits the block gas limit and the function becomes unusable.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Reward Vesting and Deferred Claim Distribution
- Match strength: High
- Match evidence: Both describe tranche/window-based reward distribution with checkpointing, rate rollover, accrued reward calculation, and claim payout from shared custody.

#### Checklist
- [ ] Check whether: [H-01] `RewardThrottle.checkRewardUnderflow()` might track the cumulative `APR`s wrongly.
  - Severity: High
  - Historical root cause: An internal reward-distribution helper skips writing forward the epoch aggregate APR state when the distributed amount is zero, so later epochs inherit stale cumulative values. The accounting chain that feeds the smoothing logic then averages an incomplete APR history, because the cumulative APR snapshot is only advanced on nonzero payout paths.
  - Risk pattern: Epoch-advance logic in the reward throttle updates cumulative APR state only inside the branch where the distributed amount is nonzero; the zero-amount branch returns early without writing `cumulativeCashflowApr`, `cumulativeApr`, or the bonded-value snapshot for the skipped epoch. The downstream APR-averaging routine then reads those epoch records as if they were settled.
  - Exploit shape: A caller first allows the active epoch to lag by multiple epochs, then triggers the underflow-check path so it iterates across the missed range. For the first missed epoch, the overflow source returns a positive amount and the cumulative APR is advanced. For a later missed epoch, the overflow source is exhausted and the helper returns zero, so the epoch’s cumulative APR is not written. Afterward, any call that recomputes the target APR from the smoothing window reads the stale epoch record and derives an incorrect average, changing the protocol’s target reward rate.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] RewardThrottle: If an epoch does not have any profit, then there may not be rewards for that epoch at the start of the next epoch.
  - Severity: High
  - Historical root cause: Two public gap-filling paths diverge in whether they request missing rewards from the overflow source. One path populates historical epoch state without pulling missing capital, so any epoch that had no profit can be permanently finalized as unrewarded if that helper runs before the reward-checking path. The root cause is inconsistent settlement ordering for the same epoch state.
  - Risk pattern: One path fills missing epoch state only, while the other both fills state and requests capital from the overflow source before distributing it. The same epoch records are written by both paths, but only one path performs the compensating reward request. A separate migration helper also copies epoch data forward without performing the reward settlement step.
  - Exploit shape: An attacker or operator calls the state-filling helper for a period with missing profit before the reward-underflow path is executed. The historical epoch is then written forward without pulling any reward from the overflow source. Later, when the reward check would have distributed the missing capital, the epoch is already marked settled, so the reward is no longer recoverable.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] GolomTrader’s `_settleBalances` double counts protocol fee, reducing taker’s payout for a NFT sold
  - Severity: High
  - Historical root cause: The settlement formula multiplies the fee component by trade amount twice: once when computing the protocol fee, and again when subtracting that fee from the maker proceeds. This over-subtracts the fee from the amount owed to the taker, leaving the excess value trapped in contract balance.
  - Risk pattern: The settlement path computes `protocolfee` as per-unit fee times fill amount, then subtracts that already-scaled value inside the taker payout expression that is itself multiplied by fill amount. The fee is also paid out separately to the fee recipient, so the fee term is effectively applied twice in the taker-side accounting.
  - Exploit shape: A trader fills an order with `amount > 1`. The fill executes successfully, fee transfers occur, but the taker payout uses the doubly-scaled fee term and sends less than expected. The unpaid remainder accumulates in the contract balance instead of reaching the taker.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Cross-asset margin account balance and exposure tracking
- Category: Lending
- Definition: A multi-asset margin ledger records per-account holdings, debt, and yield snapshots while enforcing leverage, token caps, cooling-off, and solvency checks across deposits, borrows, withdrawals, and trades.

### Matched historical semantic: Debt Settlement and Liquidation Lifecycle
- Match strength: High
- Match evidence: Both track cross-margin holdings, debt snapshots, leverage/solvency checks, and liquidation thresholds across deposits, borrows, withdrawals, and trades. The extract’s multi-asset margin ledger closely matches the historical debt settlement and liquidation lifecycle around debt positions and collateralized repayment.

#### Checklist
- [ ] Check whether: [H-02] Risk of overpayment due to race condition between `repay` and `liquidateWithReplacement` transactions
  - Severity: High
  - Historical root cause: The protocol reuses a live debt position identifier across liquidation replacement while allowing repayment to target that identifier without binding the action to an expected borrower snapshot. Because borrower identity is mutable between mempool submission and execution, transaction ordering can redirect repayment to a newly assigned debtor.
  - Risk pattern: One transaction path liquidates a position and then mutates the stored borrower on the existing debt position id while retaining the same future value. Another transaction path repays solely by debt position id and performs no borrower-consistency check against user intent. Correctness therefore depends on inter-transaction ordering for the same position id.
    
    — additional pattern (from raw "[H-13] Admin of the index pool can `withdrawCredit()` after `applyCover()` to avoid taking loss for the compensation paid for a certain pool"): Credit withdrawal remains open after cover application; compensation is computed later during the payout/resume flow; the credited balance used for loss sharing can be reduced to zero between those steps.
    
    — additional pattern (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): The resume function checks only per-pool pause state; it does not inspect the caller or require an owner/operator role; it flips the shared locked flag to false once checks pass.
    
    — additional pattern (from raw "[H-08] Anyone can extend withdraw wait period by depositing zero collateral"): The deposit routine updates the timestamp used by the withdrawal delay even when the deposited amount is zero, and it is callable against any position. No ownership or positive-amount check blocks the state mutation.
  - Exploit shape: A borrower with a liquidatable position broadcasts a repayment transaction referencing only a debt position id. Before it confirms, a keeper or front-runner executes liquidation-with-replacement on that same position, preserving the id and future value but changing the borrower to a new account. The pending repayment then executes afterward and pays the reassigned debt, so the original borrower both gets liquidated and funds another borrower’s position.
    
    — additional exploit (from raw "[H-13] Admin of the index pool can `withdrawCredit()` after `applyCover()` to avoid taking loss for the compensation paid for a certain pool"): A participant waits until a pool has entered an incident-covered period and premium has accrued, withdraws credit before compensation executes, and thereby escapes future loss sharing while other LPs absorb a larger share.
    
    — additional exploit (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): An LP waits until the external pool states satisfy the pause check, calls resume from their own account, and clears the shared lock before compensation accounting is finalized.
    
    — additional exploit (from raw "[H-08] Anyone can extend withdraw wait period by depositing zero collateral"): An attacker monitors a position nearing its withdrawal window, then sends a zero-amount deposit transaction against that position just before the owner can withdraw. The owner's cooldown is reset and the attacker repeats the action as often as desired to prevent withdrawals.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] The collateral remainder cap is incorrectly calculated during liquidation
  - Severity: High
  - Historical root cause: The formula for the liquidation remainder cap confuses total collateralization threshold with excess collateral above par debt repayment. By applying the full threshold multiplier to debt value, the accounting step that limits protocol fee extraction allows protocol fees to be assessed against too much borrower collateral.
  - Risk pattern: The liquidation branch first converts debt into collateral units, subtracts debt coverage and liquidator reward from assigned collateral, and then caps the remainder with `debtInCollateral * crLiquidation / PERCENT`. The intended cap should use only the surplus portion above principal coverage, i.e. `(crLiquidation - PERCENT)`. Downstream fee calculation consumes this overstated capped remainder.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): Synth pricing is derived from current reserves rather than a manipulation-resistant oracle; both mint and burn settle at the live reserve ratio, so a transient reserve skew changes both sides of the exchange.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
    
    — additional pattern (from raw "[H-30] Newly Registered Assets Skew Consultation Results"): Pair registration can occur before the first meaningful time-weighted update; native-side average is zero or effectively zero for the new pair; the consultation loop still includes the pair’s external-price contribution; the result is biased during the initialization window.
    
    — additional pattern (from raw "[H-04] TwapOracle doesn’t calculate VADER:USDV exchange rate correctly"): Oracle price computation uses an integer decimal count in a numerator/division expression; the intended scaling factor is not exponentiated; downstream minting reads the resulting rate as authoritative input.
    
    — additional pattern (from raw "[H-08] USDV and VADER rate can be wrong"): Rate computation performs integer division on low-precision inputs; the function can return zero when the denominator dominates; downstream consumers depend on the returned rate as if it were a real market quote.
    
    — additional pattern (from raw "[H-10] calculate Loss is vulnerable to flashloan attack"): Loss calculation reads current reserve-derived price; a flashloan can move the pool before the burn; reimbursement is paid immediately; the attacker can restore the pool afterward while keeping the compensation.
    
    — additional pattern (from raw "[H-17] TWAPOracle might register with wrong token order"): Pair registration trusts caller-supplied token order; the underlying pair address may expose the opposite internal order; cumulative price fields are recorded without checking whether the returned pair order matches the requested order; later updates reuse the same association.
    
    — additional pattern (from raw "[H-34] Incorrect Accrual Of `sumNative` and `sumUSD` In Producing Consultation Results"): Multiple pair contributions are accumulated into separate global sums; the final formula treats those sums as interchangeable with per-pair products; newly registered or heterogeneous pairs can skew the aggregate; downstream logic trusts the single returned value.
    
    — additional pattern (from raw "[H-28] Incorrect Price Consultation Results"): Aggregate native and fiat values are combined in the wrong formula; the result uses division where the correct dimensional relationship requires multiplying the pairwise price terms first; the oracle output is consumed by downstream pricing logic.
    
    — additional pattern (from raw "[H-18] Attacker can claim more IL by manipulating pool price then `removeLiquidity`"): Reimbursement is computed at withdrawal time from live reserves; the LP can trade before removing liquidity; the payout is made immediately; the pool can be restored after the withdrawal.
    
    — additional pattern (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): Loss formula operates on one asset denomination; the payout path sends the raw numeric result to the reserve without conversion; the reserve asset and the pool’s native unit are not guaranteed to be parity-priced.
    
    — additional pattern (from raw "[H-06] Paying IL protection for all VaderPool pairs allows the reserve to be drained."): Loss reimbursement is applied to every pool pair; pair eligibility is not bounded by a whitelist or similar validation; the reimbursement formula trusts whatever initial pool composition the attacker sets up; the reserve is the common payout source.
    
    — additional pattern (from raw "[H-07] VaderReserve does not support paying IL protection out to more than one address, resulting in locked funds"): Reserve payout authorization is bound to one allowed caller; more than one router path can invoke reimbursement logic; the router-restricted claim is executed as part of liquidity removal, so a revert blocks the entire withdrawal flow.
    
    — additional pattern (from raw "[H-02] Redemption value of synths can be manipulated to drain `VaderPool` of all native assets"): Mint/redemption amounts are derived from current pool reserves; no time-weighted or otherwise manipulation-resistant oracle is used; the attacker can move the reserve ratio with flash liquidity, mint during the distortion, then restore the pool and burn after the price normalizes.
    
    — additional pattern (from raw "[H-32] Covering impermanent loss allows profiting off asymmetric liquidity provision at expense of reserve holdings"): Loss computation uses original deposit amounts and current withdrawal amounts; asymmetric additions are allowed; the reimbursement path cannot distinguish market IL from provider-induced skew; payout comes from reserve holdings.
    
    — additional pattern (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): In the cap-setting flow, the strategy is trimmed to the new limit and the vault accounting update uses the strategy's remaining balance rather than the delta removed; the mutated vault balance field is later read by aggregate balance queries and redemption math.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
    
    — additional pattern (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): The balance aggregator normalizes on-hand token balances but directly adds the controller-reported strategy balance without scaling it to the same precision. Any consumer of the total-balance view then inherits the mixed-unit result.
  - Exploit shape: A borrower maintains collateral above debt value and later becomes overdue. When a liquidator closes the position, the protocol computes remainder collateral after debt coverage and liquidator reward, then caps that remainder using the full liquidation ratio. For borrowers with higher collateral ratios, more excess collateral remains below this inflated cap, allowing the protocol fee to be taken from a larger base than intended.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): An attacker flashloans and distorts the reserve ratio, mints synths at the inflated value, restores the price, then burns the synths at a cheaper redemption rate and extracts the difference from the pool.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
    
    — additional exploit (from raw "[H-30] Newly Registered Assets Skew Consultation Results"): An attacker registers a new asset pair and immediately triggers consultation before the pair has been updated. The oracle incorporates the fresh external price while the native-side aggregate remains zero, producing a skewed output that can be used to misprice protocol actions.
    
    — additional exploit (from raw "[H-04] TwapOracle doesn’t calculate VADER:USDV exchange rate correctly"): A caller invokes the consultation path on a pair whose token has nontrivial decimals. Because the oracle applies the wrong scale, the returned price is misquoted and any minting mechanism that consumes it mints or values assets incorrectly. Users and integrators relying on the quoted rate can be misled into executing at a faulty price.
    
    — additional exploit (from raw "[H-08] USDV and VADER rate can be wrong"): A caller queries the consultation path under conditions where the scaled numerator is smaller than the denominator. The oracle returns zero instead of a meaningful exchange rate, and any minting or pricing logic that consumes the result uses a broken valuation.
    
    — additional exploit (from raw "[H-10] calculate Loss is vulnerable to flashloan attack"): The attacker acquires an LP position, waits for reimbursement eligibility, borrows large capital, trades to distort the pool price, triggers the burn path to receive inflated impermanent-loss compensation, then reverses the trade. The reserve pays out based on the transient price instead of a resistant benchmark.
    
    — additional exploit (from raw "[H-17] TWAPOracle might register with wrong token order"): A caller registers a pair whose internal ordering differs from the supplied token ordering. The oracle records the wrong cumulative series for each side, and later price consultations produce inverted quotes that can be consumed by other protocol logic.
    
    — additional exploit (from raw "[H-34] Incorrect Accrual Of `sumNative` and `sumUSD` In Producing Consultation Results"): A caller queries consultation after several heterogeneous pairs have been registered. Because the oracle aggregates the terms separately, the output is distorted relative to the true average of each pair’s price relationship, and any mint or valuation action that trusts the result can be misled.
    
    — additional exploit (from raw "[H-28] Incorrect Price Consultation Results"): A caller queries the oracle for a target token and receives a misdimensioned quote. Any mint, redeem, or accounting action that trusts the quote will settle at the wrong rate, which can be exploited to obtain value or to make other users transact at a broken price.
    
    — additional exploit (from raw "[H-18] Attacker can claim more IL by manipulating pool price then `removeLiquidity`"): The attacker deposits liquidity, waits until some reimbursement has accrued, performs a large swap that skews the pool, withdraws liquidity to capture inflated impermanent-loss compensation, and then trades back to restore the original pool balance. The excess compensation is funded by the reserve.
    
    — additional exploit (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): A user withdraws after experiencing some impermanent loss in the pool’s accounting units. The contract computes the loss in one denomination but transfers the same number of reserve tokens without applying the actual exchange rate, so the user can over- or under-collect relative to the true loss. If the pair is sufficiently mispriced, the payout can be exploited for excess reserve extraction.
    
    — additional exploit (from raw "[H-06] Paying IL protection for all VaderPool pairs allows the reserve to be drained."): The attacker establishes or uses a pair with skewed initial liquidity, positions the asset so it will appreciate in the pool’s accounting terms, waits for reimbursement eligibility, and then withdraws to claim a large reserve payout. By choosing a toxic pair, the attacker can extract value that exceeds their real economic exposure.
    
    — additional exploit (from raw "[H-07] VaderReserve does not support paying IL protection out to more than one address, resulting in locked funds"): A user adds liquidity through a router that is not the one approved by the reserve. When they later try to remove liquidity, the router’s claim to the reserve reverts, which causes the withdrawal transaction to fail. If governance cannot update the approved claimant, that liquidity remains effectively locked.
    
    — additional exploit (from raw "[H-02] Redemption value of synths can be manipulated to drain `VaderPool` of all native assets"): The attacker flash borrows capital, performs a large trade that makes the target asset appear very valuable, mints synthetic assets with a comparatively small deposit, reverses the trade so the target asset returns to normal or lower value, then burns the synthetic assets to withdraw more native assets than were deposited. The cycle can be repeated whenever profitable.
    
    — additional exploit (from raw "[H-32] Covering impermanent loss allows profiting off asymmetric liquidity provision at expense of reserve holdings"): The attacker adds liquidity asymmetrically, optionally performs a swap or two to move the price further, waits for reimbursement eligibility, and then removes liquidity to collect loss coverage. The reserve pays for part of the attacker-created imbalance, letting the attacker recover more value than they exposed to market risk.
    
    — additional exploit (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): An authorized operator reduces a strategy cap below its current balance. The function withdraws the excess, but the vault ledger is decremented by the full strategy balance. Subsequent users deposit into the vault or redeem shares against the understated balance, receiving distorted share amounts and causing value loss for existing depositors. In some states, a later withdrawal path reverts because the internal accounting no longer matches available liquidity.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
    
    — additional exploit (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): An attacker chooses a vault configuration where the strategy-side asset uses fewer decimals than the vault's internal normalization. They deposit into the vault and observe that the total balance is understated relative to reality, then use that distorted figure to receive an unfair share allocation or to redeem for an amount that does not match the true asset value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-04] Users won’t liquidate positions because the logic used to calculate the liquidator’s profit is incorrect
  - Severity: High
  - Historical root cause: The reward formula mixes incompatible units across accounting steps: collateral-side balances are maintained in collateral-token precision while the reward cap is derived from the borrow-side amount without conversion. This unit mismatch shrinks the incentive payment and breaks liquidation economics.
  - Risk pattern: In the profitable liquidation branch, assigned collateral and debt value are compared in collateral-token units, but the reward cap uses the raw future debt amount multiplied by the liquidation reward percentage. The reward payout path then adds this understated reward to the liquidator’s collateral proceeds.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-02] set cap breaks vault’s Balance"): The strategy-cap update mutates the per-vault balance ledger with the wrong quantity; later withdrawal code expects the recorded vault balance and strategy balances to be internally consistent and reverts if they are not.
    
    — additional pattern (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): In the cap-setting flow, the strategy is trimmed to the new limit and the vault accounting update uses the strategy's remaining balance rather than the delta removed; the mutated vault balance field is later read by aggregate balance queries and redemption math.
  - Exploit shape: A liquidatable position appears onchain with enough assigned collateral to pay a reward. A liquidator evaluates the transaction and finds that the reward credited by the protocol is tiny because it was computed from a value expressed in a lower-decimal debt unit rather than collateral units. Rational liquidators skip the trade, leaving unhealthy debt outstanding and allowing bad debt risk to accumulate.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-02] set cap breaks vault’s Balance"): An operator sets a strategy cap just below its current balance. The cap logic updates the vault ledger incorrectly. A user then submits a withdrawal that depends on the controller's balance invariant; the call reverts once the inconsistent accounting is detected, so assets remain stuck in the strategy and the user cannot complete redemption.
    
    — additional exploit (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): An authorized operator reduces a strategy cap below its current balance. The function withdraws the excess, but the vault ledger is decremented by the full strategy balance. Subsequent users deposit into the vault or redeem shares against the understated balance, receiving distorted share amounts and causing value loss for existing depositors. In some states, a later withdrawal path reverts because the internal accounting no longer matches available liquidity.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Diversified Staked Asset Vault Minting and Redemption
- Match strength: High
- Match evidence: Both track per-account holdings and debt snapshots, enforce leverage/solvency, and handle deposits, borrows, withdrawals, and liquidations across multiple assets.

#### Checklist
- [ ] Check whether: [H-01] Re-balancing the vault allocation may always revert when distributing profits: resulting of a massive system DOS
  - Severity: High
  - Historical root cause: A profit-distribution path computes and writes a per-unit loss/error term even when the offset amount is zero. When a prior liquidation has already created a nonzero rounding error, the subsequent rebalance path tries to apply a negative correction to an unsigned accumulator and reverts before profit can be distributed or the rebalance can complete.
  - Risk pattern: A rebalance routine compares live vault asset value against an internal allocated amount, then subtracts a recorded loss/error term from an unsigned accumulator; the loss/error term may already be nonzero from prior offset accounting; the offending subtraction is executed even when no debt offset is being processed; downstream rebalance callers include user-facing collateral/debt adjustment flows.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-02] set cap breaks vault’s Balance"): The strategy-cap update mutates the per-vault balance ledger with the wrong quantity; later withdrawal code expects the recorded vault balance and strategy balances to be internally consistent and reverts if they are not.
    
    — additional pattern (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): In the cap-setting flow, the strategy is trimmed to the new limit and the vault accounting update uses the strategy's remaining balance rather than the delta removed; the mutated vault balance field is later read by aggregate balance queries and redemption math.
    
    — additional pattern (from raw "[H-06] earn results in decreasing share price"): Vault-level balance aggregation sums normalized token balances from the vault itself, while controller-level balance aggregation adds only the strategy's want-side balance without applying a common price conversion. The earn path updates strategy balances using those mismatched units, so total value accounting becomes inconsistent across components.
    
    — additional pattern (from raw "[H-09] `removeToken` would break the vault/protocol."): The manager's token-removal flow updates the token registry without checking that vault-local balances and strategy balances for that asset are zero or migrated. Later balance and share-price code assumes the registry reflects the live asset set.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
    
    — additional pattern (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): The balance aggregator normalizes on-hand token balances but directly adds the controller-reported strategy balance without scaling it to the same precision. Any consumer of the total-balance view then inherits the mixed-unit result.
  - Exploit shape: 1) Let the strategy accrue profit so the rebalance branch is active. 2) Trigger a liquidation/offset that creates a nonzero rounding error in the loss accumulator. 3) Call any user action that routes through rebalance; the transaction reverts during reward update. 4) Repeatable effect: trove lifecycle and liquidation/redeem operations that depend on this rebalance remain blocked whenever the stale error state is present.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-02] set cap breaks vault’s Balance"): An operator sets a strategy cap just below its current balance. The cap logic updates the vault ledger incorrectly. A user then submits a withdrawal that depends on the controller's balance invariant; the call reverts once the inconsistent accounting is detected, so assets remain stuck in the strategy and the user cannot complete redemption.
    
    — additional exploit (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): An authorized operator reduces a strategy cap below its current balance. The function withdraws the excess, but the vault ledger is decremented by the full strategy balance. Subsequent users deposit into the vault or redeem shares against the understated balance, receiving distorted share amounts and causing value loss for existing depositors. In some states, a later withdrawal path reverts because the internal accounting no longer matches available liquidity.
    
    — additional exploit (from raw "[H-06] earn results in decreasing share price"): A user deposits the base asset into the vault and waits for yield realization. Another actor triggers the earn path, which moves funds into the strategy and updates accounting in a different unit than the vault uses for its total-value calculation. After the call, the reported share price is lower than before, so all holders can redeem for less than their prior claim.
    
    — additional exploit (from raw "[H-09] `removeToken` would break the vault/protocol."): An authorized operator removes an asset from a vault before migrating its live balance. The vault still holds or has deployed that asset, but the registry no longer tracks it. Subsequent withdrawals and balance queries misprice the vault and can strand the removed asset, preventing users from redeeming the true value.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
    
    — additional exploit (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): An attacker chooses a vault configuration where the strategy-side asset uses fewer decimals than the vault's internal normalization. They deposit into the vault and observe that the total balance is understated relative to reality, then use that distorted figure to receive an unfair share allocation or to redeem for an amount that does not match the true asset value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Cross-margin account lifecycle and exposure registration
- Category: Lending
- Definition: A router-facing margin layer records deposits, borrows, withdrawals, and account closure while synchronizing protocol-wide token exposure and debt repayment.

### Matched historical semantic: Factory-Managed Safe Creation and Registry
- Match strength: High
- Match evidence: Both are router/factory-style account lifecycle systems that create user vaults/safes, register them in protocol state, and wire them into lending permissions. The extract’s account closure, borrowing, and trade registration fit the same deployment-and-registry pattern.

#### Checklist
- [ ] Check whether: [H-02] TurboRouter: `deposit()`, `mint()`, `createSafeAndDeposit()` and `createSafeAndDepositAndBoost()` functions do not work
  - Severity: Medium
  - Historical root cause: A router-level deposit/mint flow forwards execution to a vault deposit path that pulls tokens from `msg.sender`, but the router itself is the caller at that point and has not first received tokens or granted allowance to the newly created vault, so the external token transfer fails and the public entrypoints revert.
  - Risk pattern: Public router entrypoints call into a shared router base, which then calls the vault's deposit/mint logic. That logic performs `safeTransferFrom(msg.sender, address(this), amount)` from the vault side, where `msg.sender` is the router during the nested call. The router does not first transfer the user's tokens into itself nor approve the vault before invoking the downstream deposit path, so the token pull reverts. The create-and-deposit variants additionally deploy a new vault at an unpredictable address before attempting the pull, preventing any pre-approval pattern from being in place.
  - Exploit shape: A user calls one of the router's deposit-style entrypoints with their wallet as the intended source of funds. The router immediately forwards into the vault deposit path without staging funds or allowance. The vault tries to pull tokens from the router, the transfer fails, and the whole transaction reverts. An attacker does not gain funds, but any user relying on these entrypoints is blocked until the flow is corrected.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Diversified Staked Asset Vault Minting and Redemption
- Match strength: High
- Match evidence: The router-facing margin lifecycle matches the same cross-margin exposure registration, debt repayment, collateral updates, cooling-off withdrawals, and solvency revalidation seen in the historical margin semantics.

#### Checklist
- [ ] Check whether: [H-04] Price of sfrxEth derivative is calculated incorrectly
  - Severity: High
  - Historical root cause: The adapter's price conversion divides by the oracle value after multiplying by a fixed scale in the wrong order, which flips the intended conversion relationship. This produces a systematically mispriced derivative valuation that then feeds share minting and withdrawal slippage limits.
  - Risk pattern: The adapter valuation routine computes a converted amount using fixed-point arithmetic in the wrong direction relative to the oracle price. The same routine is consumed by both stake-time share minting and withdraw-time minimum-output calculation. As a result, the same bug affects entry pricing and exit slippage bounds.
  - Exploit shape: (1) A user stakes through the mispriced adapter. (2) The staking path uses the incorrect conversion result to compute the portfolio value and mint amount. (3) On withdrawal, the same bad price feeds the minimum acceptable output for the unwind swap. (4) Depending on market conditions, the user either receives too few shares / too much or too little ETH, or the withdrawal reverts and blocks unstake().
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] An attacker can manipulate the preDepositvePrice to steal from other users
  - Severity: High
  - Historical root cause: The share-minting path prices new deposits from a live asset-value estimate, but that estimate can be pushed away from the true per-share value by an attacker who changes the contract's observed derivative balances and then reduces their own share balance. Because the mint formula divides the current stake value by the pre-deposit price without any invariant check or rounding protection, a manipulated price can collapse the minted share amount for later depositors.
  - Risk pattern: Stake uses the current derivative balances to compute a pre-deposit share price, then mints new shares from current deposit value divided by that price. The observed derivative balance can be inflated by direct token transfers into the derivative adapter, while the attacker can first stake and then unstake almost all of their own shares to leave total supply extremely small. Subsequent mint calculations use the manipulated ratio and round down.
  - Exploit shape: (1) Attacker stakes a large amount to become the first or dominant share holder. (2) Attacker withdraws almost all of their shares, leaving total supply tiny. (3) Attacker donates underlying asset directly to one derivative adapter to inflate the tracked backing value. (4) A victim calls stake() and receives an extremely small or zero share mint because the computed price is inflated. (5) Attacker retains most of the shares and later redeems a disproportionate share of the pooled assets.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] `WstEth` derivative assumes a `~1=1` peg of stETH to ETH
  - Severity: High
  - Historical root cause: The unwind path sets a minimum acceptable output by applying slippage directly to the wrapped-asset amount, implicitly treating the wrapped staking receipt and the base asset as equal value. If the market exchange rate drifts below that implicit peg, the downstream swap reverts and the adapter cannot be unwound.
  - Risk pattern: The adapter's valuation routine effectively assumes wrapped-to-base conversion at par, and the withdrawal routine computes minimum output as base-asset balance minus a slippage percentage without reference to live exchange rate. The withdrawal uses a hard minimum output on the external swap, so any depeg larger than the tolerance breaks the path. The same path is invoked from user exits and owner rebalancing.
  - Exploit shape: (1) The market price of the wrapped staking receipt falls below the adapter's tolerated slippage band. (2) A user calls unstake() or the owner calls rebalanceToWeights(). (3) The adapter unwraps the position and attempts to swap the base asset for ETH with a minimum output that is now too high. (4) The external swap reverts, blocking the entire top-level operation.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Gas Deposit and Stake Management
- Match strength: High
- Match evidence: The extract and 304 both implement router-facing margin lifecycle accounting with deposits, borrows, withdrawals, exposure updates, and close conditions coordinated at protocol level.

#### Checklist
- [ ] Check whether: [H-05] Paymaster ETH can be drained with malicious sender
  - Severity: High
  - Historical root cause: The paymaster approval signature is replayable because the validation path does not bind the signed authorization to one-time use. A sender can reuse a previously accepted paymaster signature with a modified account implementation that omits the expected replay protection, causing repeated sponsor-funded payments.
  - Risk pattern: Paymaster validation accepts an authorization hash without storing or checking a consumed flag; replay protection depends on account-side behavior that can be changed by the sender; sponsor payment is taken from a shared deposit balance; repeated identical user operations remain valid under the same signature.
    
    — additional pattern (from raw "[H-03] Signature replay attacks for different identities (nonce on wrong party)"): Nonce state is tracked per target identity instead of the signing authority; the authorization digest omits the destination identity; identical initial nonce state across accounts yields reusable signatures across multiple identities.
  - Exploit shape: A sender first obtains a valid sponsored-operation signature, then switches to an implementation or account variant that does not prevent nonce reuse. The sender repeatedly submits the same operation with the same paymaster signature, and each execution deducts sponsor funds again until the deposit is exhausted.
    
    — additional exploit (from raw "[H-03] Signature replay attacks for different identities (nonce on wrong party)"): An attacker replays a valid signed action against a second account that shares the same signer setup and fresh nonce, causing the same state transition to execute again on the wrong target.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Cross-margin liquidation aggregation and keeper reward settlement
- Category: Lending
- Definition: A liquidation flow batches undercollateralized accounts, nets asset sales against debt purchases, and rewards or penalizes maintenance actors based on authorization and delinquency.

### Matched historical semantic: Configurable Boost Authorization and Fee Governance
- Match strength: High
- Match evidence: Both combine liquidation/maintenance flows with maintainer authorization, attack or delinquency handling, and penalties or rewards tied to upkeep performance. The extract’s keeper reward settlement and maintainer stake punishment directly mirror the historical boost/fee governance around authorized upkeep.

#### Checklist
- [ ] Manually review this semantic; a historical semantic matched, but no linked findings were found.

## Single-pair margin position lifecycle and liquidation
- Category: Lending
- Definition: A one-pair margin module tracks a single collateral and debt asset, supports opening and unwinding leveraged positions, and liquidates undercollateralized accounts through a paired asset swap route.

### Matched historical semantic: Constant-Product Lending Pool Lifecycle
- Match strength: High
- Match evidence: Both are leveraged lending modules that track a single collateral/debt pair, enforce maintenance thresholds, and liquidate undercollateralized accounts through asset swap routes. The extract’s single-pair margin lifecycle closely matches the historical pool’s maturity-gated borrowing and repayment structure.

#### Checklist
- [ ] Check whether: [H-01] Wrong timing of check allows users to withdraw collateral without paying for the debt
  - Severity: High
  - Historical root cause: The repayment loop updates per-position debt and collateral, but the solvency check is performed before those loop-local updates are incorporated into the aggregate repayment totals. As a result, the first iteration compares zero accumulated repayment against the position’s outstanding debt and collateral, so the intended proportionality check is vacuously satisfied and never enforces that the debt reduction is actually paid for before collateral is released.
  - Risk pattern: In the repayment path, the loop reads a stored debt position, performs a proportionality require using the running aggregate repayment variables while they are still zero, and only then subtracts per-item debt and collateral and increments the aggregates. The check therefore depends on state that has not yet been updated for the current iteration, and the post-loop accounting does not retroactively validate the already-released collateral.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
    
    — additional pattern (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): The withdrawal routine computes a normalized amount from share value, compares it to a raw token balance, and subtracts the raw balance from the normalized target to derive a controller withdrawal request. The post-withdraw adjustment also mixes raw and normalized quantities.
  - Exploit shape: An attacker who controls a debt position calls the repayment entrypoint with one position id, sets the per-item asset input to zero, and sets the per-item collateral output to the full remaining collateral. On the first iteration, the aggregate repayment variables are still zero so the proportionality check passes. The loop then burns down the stored debt and releases the collateral, letting the attacker keep the borrowed assets while reclaiming the locked collateral.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
    
    — additional exploit (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): An attacker redeems a small number of shares for a low-decimal output asset. Because the code compares normalized and raw balances, it computes a bogus deficit and asks the controller for an inflated top-up. The attacker then receives an excessive amount of the output asset relative to their shares, draining value from the pool.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Collateral Liquidation with Optional Swapper
- Match strength: High
- Match evidence: Both describe undercollateralized margin liquidation with batch account processing, seized collateral versus debt repayment, surplus return, and maintainer/attack reward handling.

#### Checklist
- [ ] Check whether: [H-11] Incorrect protocol fee implementation results in `outstandingValues` to be mis-accounted in Pool.sol
  - Severity: High
  - Historical root cause: The liquidation-distribution callback passes a zero protocol-fee fraction into pool liquidation accounting even when the underlying loan used a nonzero fee schedule. That causes the termination path to subtract an inflated pre-fee APR from outstanding APR totals, breaking the invariant that outstanding values reflect post-fee loan economics.
  - Risk pattern: Liquidation callback hardcodes protocol fee as zero; pool termination updates sumApr using the APR passed in by the callback; outstandingValues.sumApr is consumed by later interest and accounting logic; fee-adjusted APR used on loan creation is inconsistent with liquidation-time APR.
    
    — additional pattern (from raw "[H-30] Newly Registered Assets Skew Consultation Results"): Pair registration can occur before the first meaningful time-weighted update; native-side average is zero or effectively zero for the new pair; the consultation loop still includes the pair’s external-price contribution; the result is biased during the initialization window.
    
    — additional pattern (from raw "[H-04] TwapOracle doesn’t calculate VADER:USDV exchange rate correctly"): Oracle price computation uses an integer decimal count in a numerator/division expression; the intended scaling factor is not exponentiated; downstream minting reads the resulting rate as authoritative input.
    
    — additional pattern (from raw "[H-08] USDV and VADER rate can be wrong"): Rate computation performs integer division on low-precision inputs; the function can return zero when the denominator dominates; downstream consumers depend on the returned rate as if it were a real market quote.
    
    — additional pattern (from raw "[H-17] TWAPOracle might register with wrong token order"): Pair registration trusts caller-supplied token order; the underlying pair address may expose the opposite internal order; cumulative price fields are recorded without checking whether the returned pair order matches the requested order; later updates reuse the same association.
    
    — additional pattern (from raw "[H-34] Incorrect Accrual Of `sumNative` and `sumUSD` In Producing Consultation Results"): Multiple pair contributions are accumulated into separate global sums; the final formula treats those sums as interchangeable with per-pair products; newly registered or heterogeneous pairs can skew the aggregate; downstream logic trusts the single returned value.
    
    — additional pattern (from raw "[H-28] Incorrect Price Consultation Results"): Aggregate native and fiat values are combined in the wrong formula; the result uses division where the correct dimensional relationship requires multiplying the pairwise price terms first; the oracle output is consumed by downstream pricing logic.
    
    — additional pattern (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): Loss formula operates on one asset denomination; the payout path sends the raw numeric result to the reserve without conversion; the reserve asset and the pool’s native unit are not guaranteed to be parity-priced.
    
    — additional pattern (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): In the cap-setting flow, the strategy is trimmed to the new limit and the vault accounting update uses the strategy's remaining balance rather than the delta removed; the mutated vault balance field is later read by aggregate balance queries and redemption math.
  - Exploit shape: 1) A loan funded by the pool is liquidated. 2) The settlement callback invokes pool liquidation accounting with a zero fee fraction instead of the loan’s actual fee. 3) The pool subtracts a pre-fee APR from outstanding totals. 4) Subsequent accounting and interest calculations read corrupted outstanding values, mispricing the pool’s state.
    
    — additional exploit (from raw "[H-30] Newly Registered Assets Skew Consultation Results"): An attacker registers a new asset pair and immediately triggers consultation before the pair has been updated. The oracle incorporates the fresh external price while the native-side aggregate remains zero, producing a skewed output that can be used to misprice protocol actions.
    
    — additional exploit (from raw "[H-04] TwapOracle doesn’t calculate VADER:USDV exchange rate correctly"): A caller invokes the consultation path on a pair whose token has nontrivial decimals. Because the oracle applies the wrong scale, the returned price is misquoted and any minting mechanism that consumes it mints or values assets incorrectly. Users and integrators relying on the quoted rate can be misled into executing at a faulty price.
    
    — additional exploit (from raw "[H-08] USDV and VADER rate can be wrong"): A caller queries the consultation path under conditions where the scaled numerator is smaller than the denominator. The oracle returns zero instead of a meaningful exchange rate, and any minting or pricing logic that consumes the result uses a broken valuation.
    
    — additional exploit (from raw "[H-17] TWAPOracle might register with wrong token order"): A caller registers a pair whose internal ordering differs from the supplied token ordering. The oracle records the wrong cumulative series for each side, and later price consultations produce inverted quotes that can be consumed by other protocol logic.
    
    — additional exploit (from raw "[H-34] Incorrect Accrual Of `sumNative` and `sumUSD` In Producing Consultation Results"): A caller queries consultation after several heterogeneous pairs have been registered. Because the oracle aggregates the terms separately, the output is distorted relative to the true average of each pair’s price relationship, and any mint or valuation action that trusts the result can be misled.
    
    — additional exploit (from raw "[H-28] Incorrect Price Consultation Results"): A caller queries the oracle for a target token and receives a misdimensioned quote. Any mint, redeem, or accounting action that trusts the quote will settle at the wrong rate, which can be exploited to obtain value or to make other users transact at a broken price.
    
    — additional exploit (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): A user withdraws after experiencing some impermanent loss in the pool’s accounting units. The contract computes the loss in one denomination but transfers the same number of reserve tokens without applying the actual exchange rate, so the user can over- or under-collect relative to the true loss. If the pair is sufficiently mispriced, the payout can be exploited for excess reserve extraction.
    
    — additional exploit (from raw "[H-01] `Controller.setCap` sets wrong vault balance"): An authorized operator reduces a strategy cap below its current balance. The function withdraws the excess, but the vault ledger is decremented by the full strategy balance. Subsequent users deposit into the vault or redeem shares against the understated balance, receiving distorted share amounts and causing value loss for existing depositors. In some states, a later withdrawal path reverts because the internal accounting no longer matches available liquidity.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] Function `distribute()` lacks access control allowing anyone to spam and disrupt the pool’s accounting
  - Severity: High
  - Historical root cause: A public distribution entrypoint forwards liquidation proceeds into pool accounting without restricting the caller to the trusted loan/settlement flow. Because the accounting side assumes the call reflects a legitimate liquidation with the correct principal asset and metadata, an arbitrary caller can inject mismatched settlements and drive pool state updates with attacker-chosen inputs.
  - Risk pattern: Externally callable distribution function; missing caller restriction to the trusted loan path; downstream call into pool loan-liquidation accounting; loan-manager callback triggered with attacker-supplied settlement metadata while principal-asset identity is not validated at the pool boundary.
  - Exploit shape: 1) An attacker calls the distribution function directly. 2) They supply settlement data that points to arbitrary collateral/asset context. 3) The function transfers funds and triggers pool accounting as if a valid liquidation occurred. 4) Pool bookkeeping records the proceeds against the wrong asset/loan context, spamming or corrupting accounting state.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-05] `triggerFee` is stolen from other auctions during `settleWithBuyout()`
  - Severity: High
  - Historical root cause: The buyout-settlement path pays an auction trigger fee from the contract’s shared balance instead of collecting it from the buyer who initiated the settlement. This turns a per-auction fee into a shared-pool drain, so one settlement can consume assets reserved for unrelated concurrent auctions.
  - Risk pattern: Buyout settlement pays lenders from msg.sender while paying trigger fee from contract balance; no corresponding fee collection from the buyer; multiple concurrent auctions share the same balance pool; fee transfer can revert or deplete funds reserved for other auctions.
  - Exploit shape: 1) Multiple auctions are active and their balances are commingled in the settlement contract. 2) A buyer triggers buyout settlement for one auction. 3) The function pays the fee from contract-held funds instead of from the buyer. 4) The fee either drains funds belonging to other auctions or causes later settlements to fail due to insufficient balance.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Shared custody deposits, withdrawals, and wrapped native asset handling
- Category: Services
- Definition: A custody contract accepts direct token transfers, authorized third-party transfers, and wrapped-native mint/burn flows for protocol settlement.

### Matched historical semantic: Protocol Administration and Token Distribution
- Match strength: High
- Match evidence: Both are shared custody vaults for protocol settlement. The extract’s custody contract accepts deposits, third-party authorized transfers, and native wrap/unwrap flows, which aligns with the historical administration and token distribution surface around protocol-held funds.

#### Checklist
- [ ] Check whether: [H-01] `update_emergency_council_7_D_0_C_1_C_58()` updates nft manager instead of emergency council
  - Severity: High
  - Historical root cause: The privileged state-transition for rotating the emergency authority is misbound to the wrong storage destination. The accounting step that should update the emergency-council address instead performs a write to the NFT-manager address, so the call changes unrelated authorization state and leaves the intended control unchanged.
  - Risk pattern: A role-update function guarded by an admin check mutates the wrong storage variable: the path named for emergency authority assignment stores the input address into the NFT-manager slot instead of the emergency-council slot. Two distinct admin setters therefore write the same privileged field.
    
    — additional pattern (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): The resume function checks only per-pool pause state; it does not inspect the caller or require an owner/operator role; it flips the shared locked flag to false once checks pass.
  - Exploit shape: An authorized admin calls the emergency-council update entrypoint expecting to rotate the shutdown authority. Because the implementation writes the supplied address into the NFT-manager field, the supplied address immediately becomes the NFT-management authority, while the old emergency authority stays active. The misconfigured privileged state can then be abused through whatever manager-only operations exist.
    
    — additional exploit (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): An LP waits until the external pool states satisfy the pause check, calls resume from their own account, and clears the shared lock before compensation accounting is finalized.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Users can lose value in emergency state
  - Severity: High
  - Historical root cause: The emergency withdrawal path assumes the wrapped-native reserve can still be returned to users even after that reserve has already been committed into liquidity provision. Once the liquidity-creation step zeroes out the reserve state and deposits the assets into the pool, the emergency exit logic no longer has the assets it tries to refund, so the fallback path cannot satisfy its own accounting obligations.
  - Risk pattern: Emergency mode is enabled after the reserve has been consumed in the pool-seeding step; the emergency exit path relies on the original reserve balance rather than the minted liquidity position; the paused branch blocks the normal withdrawal route; the refund logic does not switch to paying out liquidity tokens or an equivalent claim.
  - Exploit shape: An attacker or operator first calls the liquidity-seeding action so the reserve is moved into the pool, then triggers the emergency/paused state, and finally a user calls the emergency exit. The call reverts or cannot transfer the expected assets because the reserve is already gone, so the user is stuck with neither the original deposit nor a redeemable liquidity claim.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Wrong token allocation computation for token decimals != 18 if floor price not reached
  - Severity: High
  - Historical root cause: When the raised amount falls below the floor-price target, the adjusted token allocation is computed with a denominator scaled to an 18-decimal price but a numerator scaled by the token's native decimals. For non-18-decimal tokens, this mixes units incorrectly and can truncate the allocation to zero or an incorrect amount, breaking the intended proportional price-to-supply relationship.
  - Risk pattern: The floor-price branch recomputes allocated token amount using the raised native reserve multiplied by 10**tokenDecimals and divided by an 18-decimal floor price; the formula is only correct when the sold asset also uses 18 decimals; the downstream pool-seeding and distribution logic consume this derived allocation to decide how many tokens to transfer.
  - Exploit shape: A project lists a non-18-decimal asset and the sale closes below floor. The operator computes the adjusted allocation with the flawed formula, which can round to zero or another incorrect value. The liquidity seeding then transfers too few tokens relative to the native asset raised, letting the final pool composition diverge from the intended floor-price ratio.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Royalty Vault Accumulation and Forwarding
- Match strength: High
- Match evidence: Both are shared custody vaults that receive ERC20 assets and serve as the common source of funds for downstream protocol flows. The extract’s custody/deposit/withdraw mechanics match the historical royalty vault’s balance-holding and forwarding role.

#### Checklist
- [ ] Check whether: [H-06] STORAGE COLLISION BETWEEN PROXY AND IMPLEMENTATION (LACK EIP 1967)
  - Severity: High
  - Historical root cause: The proxy stores its implementation/admin metadata in ordinary storage slots instead of reserved unstructured slots, so the implementation's own state layout can overlap and overwrite proxy-critical values during upgrades or execution.
  - Risk pattern: Proxy metadata is stored in standard storage positions rather than EIP-1967-style reserved slots. The implementation and proxy share the same storage layout, so inherited variables and newly added state can collide with the proxy's administrative fields.
    
    — additional pattern (from raw "[H-10] Changing NFT contract in the `MochiEngine` would break the protocol"): A mutable engine-level address is read by vaults for ownership checks and position lookups, and the address can be replaced by an operator after live positions already exist. No migration of existing position state accompanies the change.
  - Exploit shape: An operator upgrades to a new implementation whose storage layout no longer matches the original expectation, or changes inheritance order so the first slots shift. Subsequent writes from the implementation overlap the proxy's metadata, causing the proxy to lose its admin/implementation reference or otherwise behave incorrectly.
    
    — additional exploit (from raw "[H-10] Changing NFT contract in the `MochiEngine` would break the protocol"): The operator changes the engine's NFT reference after users have opened positions. Subsequent withdraw, repay, or liquidation flows compare against the wrong ownership source, causing legitimate users to lose access to their positions and breaking the protocol's core lifecycle.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] the first depositor to a pool can drain all users
  - Severity: High
  - Historical root cause: The pool’s share-minting formula lets the first depositor define the initial liquidity baseline, and later deposits divide by that baseline without guarding against pathological low initial supply, causing rounding to zero for subsequent participants.
  - Risk pattern: First deposit sets the initial total liquidity; later share minting uses a ratio of deposited value to total liquidity; share output is integer-truncated; an attacker can inflate the effective pool value through transferable attributions while retaining nearly all shares.
  - Exploit shape: An attacker makes the first deposit with the smallest possible amount, acquiring nearly all shares. They then increase the apparent pool value through allowed attribution transfers. When a victim deposits a large amount, the share formula rounds down to zero, so the victim receives no meaningful ownership while the attacker later redeems the combined pool value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] The return value of the _sendForReceiver function is not set, causing the receiver to receive more fees
  - Severity: High
  - Historical root cause: The fee distribution loop relies on a boolean success signal to decide whether unspent allocation should carry forward, but the non-contract payout branch performs a transfer without returning a success value. That implicit false result makes the distributor treat a successful payout as a failure, so leftover accounting is preserved incorrectly and future rounds over-credit the same allocation.
  - Risk pattern: A distribution loop computes amountToSend, calls a helper that is expected to return a completion flag, and conditionally preserves leftover only on failure. In the branch for non-contract recipients, the helper performs a token transfer but falls through without an explicit boolean return, so the caller receives the default false value and updates leftover as if the payout had failed.
    
    — additional pattern (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): Collateral-send path calls unwrap before reward update; user reward state remains stale at the moment the wrapped collateral is burned/removed; later reward claims can still read the pre-withdrawal balance and pay out yield on exited collateral.
    
    — additional pattern (from raw "[WM-04] ActivePool does not update rewards before unwrapping wrapped asset"): Collateral transfer routine performs unwrap before reward claim/update; wrapper commentary indicates rewards should be updated prior to burn; reward update reads stake and reward debt after the unwrap has already changed the user balance.
  - Exploit shape: (msg.sender = distributor caller) triggers a normal fee distribution that includes an externally owned recipient. The helper sends tokens successfully to that recipient, but returns false by default; the loop stores the amount as leftover and carries it into later recipients and later distributions, inflating subsequent payouts and corrupting reward allocation.
    
    — additional exploit (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): A collateral manager unwraps a user’s wrapped position and only later updates rewards; because the reward ledger reads the post-burn state, the user can either lose accrued yield or keep claiming against stale stake, depending on the direction of the accounting error.
    
    — additional exploit (from raw "[WM-04] ActivePool does not update rewards before unwrapping wrapped asset"): A user with wrapped collateral accrues rewards, then the pool sends the collateral out and only afterward updates rewards; the pre-withdrawal entitlement is no longer reflected correctly, so later distribution can misallocate value based on stale state.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Shared Vault Deposit, Withdrawal, Share Transfer, and Flash Loan
- Match strength: High
- Match evidence: This is the same shared custody/vault layer used by the staking, lending, and incentive flows: deposits, withdrawals, and wrapped-native handling are all moved through a common fund contract.

#### Checklist
- [ ] Check whether: [H-09] treasury is vulnerable to sandwich attack
  - Severity: High
  - Historical root cause: A permissionless treasury rebalance uses the live market price at execution time without any slippage bound or time-weighted pricing. An attacker can manipulate the price in the same block around the treasury trade, making the treasury execute at an adversarial rate and transferring value to the attacker.
  - Risk pattern: Public treasury execution reads the current pool price and swaps without a minimum-return constraint. The attack relies on ordering the attacker trade before the treasury call and the unwind trade after it in the same block.
  - Exploit shape: The attacker borrows capital, pushes the market price of the target asset upward, calls the public treasury execution so the treasury buys at the manipulated price, and then sells the asset back to restore the market and repay the loan. The difference is extracted from treasury funds.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-13] Tokens Can Be Stolen By Frontrunning `VestedRewardPool.vest()` and `VestedRewardPool.lock()`
  - Severity: High
  - Historical root cause: The vesting and locking flows assume a prior token transfer has already allocated the deposited amount to the intended beneficiary, but the public entrypoints do not bind the transfer and vesting actions into one authenticated sequence. Because the balance-moving step is not enforced by the contract, a third party can front-run the public call and redirect the recorded vesting claim.
  - Risk pattern: Public vest/lock logic depends on an off-chain or prior token transfer assumption rather than a single authenticated call that atomically transfers and records the stake. The state transition that records the vesting recipient is reachable before the intended user's transaction lands.
  - Exploit shape: A victim submits a transaction intended to vest or lock tokens for their own account. An attacker sees it in the mempool, races a transaction with the same setup, and gets their call mined first so the recorded vesting position captures the tokens or claim rights instead of the victim's.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-11] `treasuryShare` is Overwritten in `FeePoolV0._shareMochi()`
  - Severity: High
  - Historical root cause: The reward-sharing helper clears the treasury share even though the underlying base asset remains in the fee pool and has not yet been sent to the treasury. This lets callers of the public distribution path reclassify remaining balances and repeatedly convert treasury-bound value into reward-distributed value.
  - Risk pattern: A public distribution path calls a helper that sets both the reward accumulator and the treasury accumulator to zero after only sending out reward-side proceeds. The remaining base tokens stay in the contract and can be reallocated by a later reserve update.
  - Exploit shape: A user triggers reward distribution before the treasury payout path runs, causing the treasury share to be zeroed. The user then calls the reserve update routine on the still-held base tokens and repeats the cycle so that tokens intended for the treasury are progressively diverted to reward recipients.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Governed Asset Custody and Routed Execution
- Match strength: High
- Match evidence: Both are shared custody vaults that accept direct or authorized transfers of tokens and native assets and serve as a fund source for other protocol flows.

#### Checklist
- [ ] Check whether: [H-04] AaveVault does not update TVL on deposit/withdraw
  - Severity: High
  - Historical root cause: The vault mints shares from a cached total-value snapshot without first recomputing the balance after accrued interest has changed the underlying rebasing token balance. A depositor can therefore be priced against an outdated asset base, then force the cached value to refresh and redeem shares against the higher post-interest value, capturing accumulated yield that belonged to existing depositors.
  - Risk pattern: A cached TVL variable is read to determine shares to mint, but the cache is not updated before the deposit path runs. The underlying asset balance grows passively over time, and a later update step incorporates that growth into the cached value after the attacker has already received shares based on the older value.
  - Exploit shape: An attacker waits until interest has accumulated in the rebasing asset balance, then deposits a large amount through the vault while the cached TVL is still stale. The deposit is priced too cheaply, the internal value snapshot is refreshed to include both the deposit and the accrued interest, and the attacker immediately withdraws the newly minted shares for more assets than they contributed, taking a portion of the previously accrued interest.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] `UniV3Vault.sol#collectEarnings()` can be front run
  - Severity: High
  - Historical root cause: The share minting and redemption logic prices deposits using a vault total-value measure that excludes unclaimed trading fees. Because the fee-collection transaction and a deposit transaction can be reordered within the same block, an attacker can enter before the fee realization at the stale price and exit after the fees are added, capturing value that should have accrued to prior LPs.
  - Risk pattern: Deposit share minting reads a TVL value that omits uncollected fees, while the strategy later realizes those fees in a separate transaction. The attacker can place a deposit transaction ahead of the fee-collection transaction in the same block, then withdraw after the fee state is updated and claim part of the newly included earnings without having borne the prior risk period.
  - Exploit shape: A strategy submits a transaction to collect and reinvest accumulated fees. An attacker sees it in the mempool and submits a deposit with a higher gas price so it executes first against stale TVL. After the strategy transaction lands and fees are added to vault value, the attacker submits a withdrawal and extracts a pro-rata portion of those fees, capturing value from earlier LPs.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Shared Collateral Vault Deposit and Withdrawal
- Match strength: High
- Match evidence: Both are shared custody vaults that accept deposits, hold user funds in protocol custody, and later release withdrawals through controlled transfer paths.

#### Checklist
- [ ] Check whether: [H-05] `Withdrawable.withdraw` does not decrease `pendingWithdrawals`
  - Severity: High
  - Historical root cause: The withdrawal routine pays out funds without decrementing the corresponding pending-withdrawal liability. As a result, reserve accounting continues to treat already-withdrawn amounts as if they were still owed, which suppresses the reported reserve balance and propagates the wrong value into minting calculations.
  - Risk pattern: A storage variable tracking pending withdrawals is increased on request creation but never reduced in the withdrawal path; reserve-balance reads continue subtracting the unchanged liability from gross holdings; mint math consumes the distorted reserve balance.
  - Exploit shape: A user creates a withdrawal obligation and later withdraws it successfully. The liability stays in storage. Subsequent reserve reads still treat the withdrawn amount as outstanding, so later mint operations are computed against an artificially reduced reserve and issue the wrong amount.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Router-mediated cross-margin funding and invariant-preserving AMM swap settlement
- Category: Dexes
- Definition: A router coordinates margin deposits, withdrawals, borrows, and multi-hop AMM swaps while enforcing end-state balance checks across the swap route.

### Matched historical semantic: Router-Forwarded Safe Operations
- Match strength: High
- Match evidence: Both are router-mediated execution layers that forward user actions, handle wrapped native asset paths, and coordinate multi-hop swaps with end-state checks. The extract’s margin funding and AMM settlement fit the historical safe-operation/router forwarding pattern closely.

#### Checklist
- [ ] Check whether: [H-01] ERC4626 mint uses wrong `amount`
  - Severity: High
  - Historical root cause: The vault mints shares using the asset-denominated `amount` computed from the preview path instead of minting the requested share quantity, so the share supply is incremented by the wrong unit and asset/share exchange-rate accounting drifts whenever the ratio is not 1:1.
  - Risk pattern: In the mint path, the previewed asset cost is stored in `amount`, `asset.safeTransferFrom` pulls that amount from the caller, and `_mint(to, amount)` credits the same value as shares. The invariant that minted shares should equal the requested share amount is broken, so any later redeem path that values shares against total assets can be exploited after the share price has moved away from 1:1.
    
    — additional pattern (from raw "[H-02] wrong minting amount"): A mint amount variable is derived from `baseBalance * ONE / redeemRate` instead of the transfer delta; the result depends on the contract’s live balance before/after the call rather than on the user’s deposit amount; downstream issuance uses that computed value as the minted supply.
    
    — additional pattern (from raw "[H-06] the first depositor to a pool can drain all users"): First deposit sets the initial total liquidity; later share minting uses a ratio of deposited value to total liquidity; share output is integer-truncated; the attacker can inflate the effective pool value while retaining nearly all shares.
    
    — additional pattern (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): The withdrawal routine computes a normalized amount from share value, compares it to a raw token balance, and subtracts the raw balance from the normalized target to derive a controller withdrawal request. The post-withdraw adjustment also mixes raw and normalized quantities.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
    
    — additional pattern (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): The balance aggregator normalizes on-hand token balances but directly adds the controller-reported strategy balance without scaling it to the same precision. Any consumer of the total-balance view then inherits the mixed-unit result.
  - Exploit shape: An attacker waits until the vault has positive yield so total assets exceed total supply, then calls the mint path with a desired share amount. They pay only the previewed asset cost but receive an equal number of shares to the asset amount rather than the requested shares. They then redeem those shares for a larger asset amount than paid, repeating until the exchange rate is pushed back toward parity.
    
    — additional exploit (from raw "[H-02] wrong minting amount"): An attacker chooses a deposit timing when the contract base balance is favorable. They call the minting path with a small or manipulated deposit. Because the calculation keys off the existing balance, the attacker receives an inflated or deflated mint amount relative to the actual deposit, extracting value from the pool of token holders.
    
    — additional exploit (from raw "[H-06] the first depositor to a pool can drain all users"): An attacker makes the first deposit with the smallest possible amount, acquires nearly all shares, then increases the apparent pool value through transferable attributions. When a victim deposits a large amount, the share formula rounds down to zero, so the attacker later redeems the combined pool value.
    
    — additional exploit (from raw "[H-08] `Vault.withdraw` mixes normalized and standard amounts"): An attacker redeems a small number of shares for a low-decimal output asset. Because the code compares normalized and raw balances, it computes a bogus deficit and asks the controller for an inflated top-up. The attacker then receives an excessive amount of the output asset relative to their shares, draining value from the pool.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
    
    — additional exploit (from raw "[H-07] `Vault.balance()` mixes normalized and standard amounts"): An attacker chooses a vault configuration where the strategy-side asset uses fewer decimals than the vault's internal normalization. They deposit into the vault and observe that the total balance is understated relative to reality, then use that distorted figure to receive an unfair share allocation or to redeem for an amount that does not match the true asset value.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Arbitrary contract call allows attackers to steal ERC20 from users’ wallets
  - Severity: High
  - Historical root cause: A swap helper forwards attacker-controlled calldata to an attacker-chosen external destination without restricting the callee set. That lets the caller repurpose the swap execution path into an arbitrary token contract call, including a state-changing token transfer that spends allowances granted to the router.
  - Risk pattern: An internal swap-filling routine performs a low-level call to a payable destination address using attacker-supplied calldata; the destination is not validated against a whitelist or expected exchange adapter set. The same path is reachable while the router already holds token approvals from users, so the external call can be shaped into a token contract state-changing method that spends those allowances.
  - Exploit shape: Attacker waits until a victim has approved the router for some token. The attacker then submits a swap transaction with the external-call destination set to that token contract and calldata encoding a token transfer-from the victim to the attacker. The router executes the call, the token honors the allowance, and the victim’s approved balance is transferred out to the attacker.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Wrong calculation of `erc20Delta` and `ethDelta`
  - Severity: High
  - Historical root cause: The swap output accounting snapshots the contract’s post-deposit balance as the baseline, then subtracts that same snapshot from the post-swap balance. Because the baseline already includes the caller’s input, the delta calculation undercounts or zeroes the received amount and breaks downstream payout/refund logic.
  - Risk pattern: Balance snapshots are taken from the live contract balance after input funds are already present, and the code later computes deltas with a subtract-or-zero helper against that snapshot. The same issue applies to both native balance tracking and token balance tracking whenever the input asset is part of the measured balance.
  - Exploit shape: A user submits a swap with input funds included in the transaction value or transferred token amount. The router records the already-inflated balance, executes the external fill, then compares the final balance to that inflated baseline. If any refund or same-asset round trip occurs, the computed delta is smaller than the true received amount, so the contract misaccounts the result and the user receives less than expected or cannot recover the refund.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Path Quotation Across Legacy and Bin-Based Pools
- Match strength: High
- Match evidence: Both are router-mediated multi-hop swap utilities with end-state balance checks and path execution; the extract explicitly coordinates margin deposits/borrows around swaps, while 334/related router semantics cover path quotation and routed swap execution.

#### Checklist
- [ ] Check whether: [H-04] Wrong calculation in function `LBRouter._getAmountsIn` make user lose a lot of tokens when swap through JoePair (most of them will gifted to JoePair freely)
  - Severity: High
  - Historical root cause: The exact-input quote helper for legacy constant-product pools uses the wrong denominator by missing parentheses around the output-reserve decrement. That makes the computed input amount far larger than required, so the router overcollects tokens from the user while still delivering only the requested output.
  - Risk pattern: In the legacy branch of the input-amount helper, the formula uses `reserveOut - amountOut * 997` instead of `(reserveOut - amountOut) * 997`. The helper’s result is then used to pre-transfer tokens into the first hop and later reused as the expected input path, so the misquote directly affects execution.
    
    — additional pattern (from raw "[H-04] Division rounding can make fraction-price lower than intended (down to zero)"): Per-fraction price is computed via integer division of a buyout amount by total supply; the rounded value is reused as the canonical price for sell and cash flows; small-denominator edge cases can collapse the price to zero.
    
    — additional pattern (from raw "[H-06] RubiconRouter _swap does not pass whole amount to RubiconMarket"): Pre-forward amount is adjusted by subtracting `amount * feeBPS / 10000` instead of solving for the gross amount needed after downstream fee extraction; downstream market fee is applied again on the already-discounted amount; residual dust remains outside the intended swap path.
  - Exploit shape: A trader requests an exact-output swap across a route that includes a legacy constant-product pool. The router calculates an inflated input requirement, transfers that larger amount from the trader to the first pool, and then executes the swap using the requested output as the terminal amount. The trader receives the intended output but loses the surplus input that was needlessly pulled into the route.
    
    — additional exploit (from raw "[H-04] Division rounding can make fraction-price lower than intended (down to zero)"): An attacker starts a buyout with parameters that make the computed fraction price truncate to zero or one wei, then acquires fractions at that price or shifts value between participants through the mispriced cash-out path.
    
    — additional exploit (from raw "[H-06] RubiconRouter _swap does not pass whole amount to RubiconMarket"): A user routes a multi-leg swap and the router forwards too little to the market, so part of the caller’s intended input is left unforwarded or stranded as dust.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Incorrect output amount calculation for Trader Joe V1 pools
  - Severity: High
  - Historical root cause: The router’s V1 swap branch computes output as `reserve * balanceDelta * fee / balance` instead of using the constant-product denominator that preserves the invariant. This order of operations underestimates the amount out for routed swaps that traverse legacy pools, so the helper returns a systematically worse price than the actual pool math.
  - Risk pattern: In the V1 branch of the swap helper, the amount-out formula divides by the full post-trade balance instead of by the invariant-preserving denominator built from reserve plus fee-adjusted input. The same branch is used when bin step indicates the legacy pool type, so the wrong math is taken only on those paths and not on the newer pool path.
  - Exploit shape: A user submits a fee-on-transfer supporting routed swap that includes a legacy pool. The router infers the pool type, enters the legacy branch, and computes a smaller output than the pool would actually return under the correct constant-product formula. The router then executes the swap using the underestimated amount, causing the user to lose value to the pool relative to the expected route pricing.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-07] RubiconRouter.swapEntireBalance() doesn’t handle the slippage check properly
  - Severity: High
  - Historical root cause: The wrapper accepts a user-supplied minimum-output bound but transforms that bound before passing it to the underlying swap logic, so the actual slippage constraint enforced by the trade path is weaker than the caller requested. This breaks the user’s intent and allows execution under materially worse price conditions than specified.
  - Risk pattern: User-provided minimum output is rewritten before the swap helper enforces it; fee adjustment is applied to the slippage floor rather than only to the gross input/output conversion; final `require` compares against a weakened threshold rather than the original caller constraint.
  - Exploit shape: 1) A user calls the full-balance swap helper with a strict minimum-out value. 2) The helper adjusts that bound before passing it onward. 3) The route executes at a worse price than the caller intended, yet still satisfies the weakened check. 4) The caller receives fewer output tokens than their specified tolerance would have allowed.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Concentrated Liquidity AMM Swap
- Match strength: High
- Match evidence: Both are router-mediated swap execution paths with multi-hop routing and end-state balance checks. The extract explicitly forwards deposits/withdrawals and executes routed swaps, matching the historical concentrated-liquidity AMM swap and routing semantics.

#### Checklist
- [ ] Check whether: [H-07] `swapOut` functions have invalid slippage check, causing user loss of funds
  - Severity: High
  - Historical root cause: Pool state finalization stores a speculative terminal loop value rather than the last executable market state. The price field is mutated after traversal reaches the caller limit, but no corresponding liquidity-backed trade occurred at that exact price, so persisted pricing drifts away from realizable AMM state and later executions fail.
  - Risk pattern: The swap loop updates a local price on each iteration and exits when amount_remaining is zero or current price equals the user limit. Final state persistence writes the loop's current price directly to storage instead of separately tracking the last valid liquidity-backed price encountered before the terminal limit condition.
    
    — additional pattern (from raw "[H-15] `VaderRouter._swap` performs wrong swap"): A three-hop path calls the intermediate swap with swapped positional arguments; the first hop uses the wrong asset-side amount; the pool enforces a native-side balance check that the call cannot satisfy; the final hop is never reached.
    
    — additional pattern (from raw "[H-16] `VaderRouter.calculateOutGivenIn` calculates wrong swap"): The output calculator swaps the first and second pool order; the reserve arguments passed into the swap formula do not match the asset flow; the resulting quote is used as the basis for routing decisions.
  - Exploit shape: A trader initiates the two-leg swap helper across two pools. The first leg returns a stablecoin amount. The second leg starts with that amount but only partially consumes it because available liquidity is insufficient. Instead of allowing the remaining balance or handling partial fill semantics, the helper checks for exact equality between first-leg output and second-leg consumption and reverts the entire transaction.
    
    — additional exploit (from raw "[H-15] `VaderRouter._swap` performs wrong swap"): A user submits any three-hop swap. The router constructs the intermediate call with the wrong amount slot, the first pool rejects the trade due to reserve-side validation, and the transaction reverts. The failure is deterministic for the affected path length.
    
    — additional exploit (from raw "[H-16] `VaderRouter.calculateOutGivenIn` calculates wrong swap"): A caller asks for a three-hop output quote and receives a value that reflects the reverse pool order. If they build a trade using that quote, the execution may revert or settle at a materially different amount than expected.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Pre-defined limit is different from the spec
  - Severity: High
  - Historical root cause: The swap logic reads a per-denomination maximum swap amount from configuration, but the configured ceiling for the native gas asset is set to a value that is 10x higher than the documented risk limit. Because the runtime limit is used as the authoritative guard for accepting swap sizes, an attacker can route a larger-than-intended amount through the swap path before the cap rejects it, defeating the intended risk-management boundary.
  - Risk pattern: A swap-size guard consults a denomination-based maximum amount table and returns the stored ceiling for the requested asset; the stored ceiling for the native gas asset does not match the documented risk limit. Any code path that relies on this guard to enforce maximum input size inherits the misconfigured threshold.
  - Exploit shape: An attacker submits a swap for the native gas asset with an amount above the documented cap but below the live configured cap. The transaction passes the maximum-amount check, executes against the pool, and moves more value than the protocol’s stated policy allows before any later limits can intervene.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Two-Asset Liquidity Provision and Redemption
- Match strength: High
- Match evidence: Both are router-mediated AMM flows that coordinate liquidity movements and multi-hop swap settlement through pair routing, with end-state balance checks and wrapped-native support.

#### Checklist
- [ ] Check whether: [H-02] Attacker can amplify a rounding error in MagicLP to break the I invariant and cause malicious pricing
  - Severity: High
  - Historical root cause: Precision loss in branch-selection arithmetic lets a floor-rounded multiplication understate the quote required for a given base deposit. That small rounding error is then amplified because the chosen branch writes persistent target reserves used as economic anchors for later pricing, violating the intended invariant ratio.
  - Risk pattern: First-liquidity minting compares `quoteBalance` against a floor-rounded `baseBalance * ratio`; if the comparison falls to the wrong branch, share count is taken from the base side and target quote reserve is derived from a second floor-rounded multiplication; downstream swap math reads persistent target variables during R-state transitions and pricing.
    
    — additional pattern (from raw "[H-07] LP pricing formula is vulnerable to flashloan manipulation"): The valuation formula uses live pool reserves and total supply to compute LP value; the same formula feeds both burn and stake conversion paths; there is no time-weighted or manipulation-resistant price source protecting the conversion step.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-06] the first depositor to a pool can drain all users"): First deposit sets the initial total liquidity; later share minting uses a ratio of deposited value to total liquidity; share output is integer-truncated; the attacker can inflate the effective pool value while retaining nearly all shares.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): Synth pricing is derived from current reserves rather than a manipulation-resistant oracle; both mint and burn settle at the live reserve ratio, so a transient reserve skew changes both sides of the exchange.
    
    — additional pattern (from raw "[H-05] Oracle returns an improperly scaled USDV/VADER price"): The pricing routine multiplies and divides fixed-point quantities but never normalizes the final result to the system's expected 18-decimal convention; downstream mint/burn code consumes the raw return value as if it were normalized.
    
    — additional pattern (from raw "[H-20] Early user can break `addLiquidity`"): When total liquidity is zero, the first mint sets share supply equal to the raw deposit; no initial liquidity is sent to an unrecoverable address; later mints depend on that initial supply for proportional calculations.
    
    — additional pattern (from raw "[H-24] Wrong design/implementation of `addLiquidity()` allows attacker to steal funds from the liquidity pool"): Liquidity addition does not enforce symmetric deposit ratios; share issuance depends on the skewed deposit amounts; the new reserves directly influence swap pricing; the attacker can combine add-liquidity, swap, and remove-liquidity in one sequence.
  - Exploit shape: An attacker initializes or immediately seeds a newly created pool using amounts that exploit the floor-rounding boundary. The pool records target reserves at a distorted ratio while preserving apparently valid initialization. Later users trade under the assumption that the configured invariant ratio is enforced, but swap pricing reads the corrupted targets and quotes incorrectly, allowing the attacker or other traders to extract value from those mispriced trades.
    
    — additional exploit (from raw "[H-07] LP pricing formula is vulnerable to flashloan manipulation"): An attacker flash-borrows the underlying asset and trades to skew the pool ratio. While the pool is distorted, they invoke the LP valuation path to mint excess credits. They reverse the trade and repay the borrow, keeping the surplus credits or derived tokens.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-06] the first depositor to a pool can drain all users"): An attacker makes the first deposit with the smallest possible amount, acquires nearly all shares, then increases the apparent pool value through transferable attributions. When a victim deposits a large amount, the share formula rounds down to zero, so the attacker later redeems the combined pool value.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): An attacker flashloans and distorts the reserve ratio, mints synths at the inflated value, restores the price, then burns the synths at a cheaper redemption rate and extracts the difference from the pool.
    
    — additional exploit (from raw "[H-05] Oracle returns an improperly scaled USDV/VADER price"): A caller queries the feed for a normal pair and receives a mis-scaled price, causing mint, burn, or reimbursement code to overpay or undercharge by the scaling factor.
    
    — additional exploit (from raw "[H-20] Early user can break `addLiquidity`"): The attacker becomes the first liquidity provider and deposits only a tiny amount of the native side. That sets a distorted base share supply, after which later providers cannot add liquidity on fair terms because their minted shares are effectively rounded against the attacker’s tiny bootstrap position.
    
    — additional exploit (from raw "[H-24] Wrong design/implementation of `addLiquidity()` allows attacker to steal funds from the liquidity pool"): The attacker adds liquidity with one-sided or highly asymmetric amounts, receiving shares while simultaneously shifting the pool price. They then perform swaps against the distorted pool and withdraw liquidity after the trade, realizing a net gain funded by the pool’s mispriced reserves.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] Users who deposited MIM and USDB tokens into BlastOnboarding may incur losses when the pool is created via bootstrap
  - Severity: High
  - Historical root cause: The initialization path allows reserve and target variables to diverge on the first deposit when supplied amounts are off-ratio. Because later pricing formulas treat target values as invariant anchors and extrapolate from reserve-target gaps, an initial imbalance becomes an exploitable accounting distortion rather than a one-time share pricing issue.
  - Risk pattern: Pool bootstrap deposits all collected balances without enforcing ratio parity; first-deposit share logic sets reserve variables from actual balances but derives target variables from the limiting side; later pricing logic has branches that recompute an internal target from `reserve - target` excess and uses that recomputed value to quote trades.
    
    — additional pattern (from raw "[H-07] LP pricing formula is vulnerable to flashloan manipulation"): The valuation formula uses live pool reserves and total supply to compute LP value; the same formula feeds both burn and stake conversion paths; there is no time-weighted or manipulation-resistant price source protecting the conversion step.
    
    — additional pattern (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): Compensation logic computes a shortage in underlying terms, calls a coverage pool that transfers share units rather than underlying units, then feeds the undercounted result into a debt-offset check that expects full underlying coverage.
    
    — additional pattern (from raw "[H-06] the first depositor to a pool can drain all users"): First deposit sets the initial total liquidity; later share minting uses a ratio of deposited value to total liquidity; share output is integer-truncated; the attacker can inflate the effective pool value while retaining nearly all shares.
    
    — additional pattern (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): The path computes a global deduction amount, derives a per-index share as a scaled ratio, then divides the global deduction by that share instead of multiplying proportionally; the accumulated actual deduction is later compared against the global target.
    
    — additional pattern (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): The contract maintains one native-side reserve balance for both synthetic issuance backing and ordinary LP liquidity; LP mint/burn calculations read the same aggregate reserve, so withdrawals can redeem against synth-backed value.
    
    — additional pattern (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): Synth pricing is derived from current reserves rather than a manipulation-resistant oracle; both mint and burn settle at the live reserve ratio, so a transient reserve skew changes both sides of the exchange.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
    
    — additional pattern (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): Different liquidity representations coexist without a unified ownership ledger; synth-minted liquidity is not counted when normal LP shares are burned; withdrawal logic can drain all assets even though synth claims remain outstanding.
    
    — additional pattern (from raw "[H-12] Attacker can get extremely cheap synth by front-running create Pool"): New pools can be created before meaningful liquidity exists; the first liquidity provider sets the price; synthetic minting depends on that bootstrap price; there is no enforced minimum liquidity or cooling period before synth issuance.
    
    — additional pattern (from raw "[H-23] Synth tokens can get over-minted"): Minted synthetic supply increases while the corresponding reserve side remains freely available; collateral backing is not locked or deducted; later liquidity removal can empty the pool while synth supply still exists.
    
    — additional pattern (from raw "[H-18] Attacker can claim more IL by manipulating pool price then `removeLiquidity`"): Reimbursement is computed at withdrawal time from live reserves; the LP can trade before removing liquidity; the payout is made immediately; the pool can be restored after the withdrawal.
    
    — additional pattern (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): Loss formula operates on one asset denomination; the payout path sends the raw numeric result to the reserve without conversion; the reserve asset and the pool’s native unit are not guaranteed to be parity-priced.
    
    — additional pattern (from raw "[H-06] Paying IL protection for all VaderPool pairs allows the reserve to be drained."): Loss reimbursement is applied to every pool pair; pair eligibility is not bounded by a whitelist or similar validation; the reimbursement formula trusts whatever initial pool composition the attacker sets up; the reserve is the common payout source.
    
    — additional pattern (from raw "[H-02] Redemption value of synths can be manipulated to drain `VaderPool` of all native assets"): Mint/redemption amounts are derived from current pool reserves; no time-weighted or otherwise manipulation-resistant oracle is used; the attacker can move the reserve ratio with flash liquidity, mint during the distortion, then restore the pool and burn after the price normalizes.
    
    — additional pattern (from raw "[H-32] Covering impermanent loss allows profiting off asymmetric liquidity provision at expense of reserve holdings"): Loss computation uses original deposit amounts and current withdrawal amounts; asymmetric additions are allowed; the reimbursement path cannot distinguish market IL from provider-induced skew; payout comes from reserve holdings.
  - Exploit shape: Users lock two assets for a later pool launch, but the locked amounts are not matched. When the pool is created, all locked balances are deposited at once, producing reserves that exceed one side’s targets. An attacker then trades into the side with excess reserve to move the state into the branch that recalculates the opposing target, after which the attacker sells the other asset against the inflated internal target and withdraws more value than fair pricing would allow.
    
    — additional exploit (from raw "[H-07] LP pricing formula is vulnerable to flashloan manipulation"): An attacker flash-borrows the underlying asset and trades to skew the pool ratio. While the pool is distorted, they invoke the LP valuation path to mint excess credits. They reverse the trade and repay the borrow, keeping the surplus credits or derived tokens.
    
    — additional exploit (from raw "[H-08] `IndexTemplate.sol#compensate()` will most certainly fail"): An attacker or normal user triggers the payout-resume path when the index pool is insolvent; the coverage pool returns a rounded-down share amount, the index records too little compensation, and the subsequent debt offset reverts, locking the market in the paying-out state.
    
    — additional exploit (from raw "[H-06] the first depositor to a pool can drain all users"): An attacker makes the first deposit with the smallest possible amount, acquires nearly all shares, then increases the apparent pool value through transferable attributions. When a victim deposits a large amount, the share formula rounds down to zero, so the attacker later redeems the combined pool value.
    
    — additional exploit (from raw "[H-11] `PoolTemplate.sol#resume()` Wrong implementation of `resume()` will compensate overmuch redeem amount from index pools"): A user triggers resume when multiple index pools hold different credit weights; the flawed formula overestimates each pool’s redeem amount, causing some pools to compensate far more than their fair share and often reverting during the final subtraction.
    
    — additional exploit (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): A synth minter deposits native assets to back a synthetic position; a later LP burn redeems from the merged reserve, consuming the synth-backed portion; the synth minter later receives less native value than originally contributed.
    
    — additional exploit (from raw "[H-07] Redemption value of synths can be manipulated to drain `VaderPoolV2` of all native assets in the associated pair"): An attacker flashloans and distorts the reserve ratio, mints synths at the inflated value, restores the price, then burns the synths at a cheaper redemption rate and extracts the difference from the pool.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
    
    — additional exploit (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): A user mints synth exposure, another liquidity provider withdraws the normal LP position that controls the actual pool shares, and the pool is emptied before the synth holder can redeem. The synth holder is left with a claim against an asset pool that no longer contains sufficient backing.
    
    — additional exploit (from raw "[H-12] Attacker can get extremely cheap synth by front-running create Pool"): An attacker front-runs the intended first liquidity provider, initializes the pool with a skewed ratio, and then mints synthetic assets while the bootstrap price is still distorted. Because the pool can’t be revoked or corrected immediately, the attacker can mint underpriced synths before normal liquidity arrives.
    
    — additional exploit (from raw "[H-23] Synth tokens can get over-minted"): An attacker mints synths while the pool is thinly collateralized, then withdraws the liquidity that was implicitly backing those synths. The synths remain outstanding but are no longer backed by recoverable assets, and the attacker can later wait for new liquidity to arrive and redeem against it.
    
    — additional exploit (from raw "[H-18] Attacker can claim more IL by manipulating pool price then `removeLiquidity`"): The attacker deposits liquidity, waits until some reimbursement has accrued, performs a large swap that skews the pool, withdraws liquidity to capture inflated impermanent-loss compensation, and then trades back to restore the original pool balance. The excess compensation is funded by the reserve.
    
    — additional exploit (from raw "[H-09] VaderPoolV2 incorrectly calculates the amount of IL protection to send to LPs"): A user withdraws after experiencing some impermanent loss in the pool’s accounting units. The contract computes the loss in one denomination but transfers the same number of reserve tokens without applying the actual exchange rate, so the user can over- or under-collect relative to the true loss. If the pair is sufficiently mispriced, the payout can be exploited for excess reserve extraction.
    
    — additional exploit (from raw "[H-06] Paying IL protection for all VaderPool pairs allows the reserve to be drained."): The attacker establishes or uses a pair with skewed initial liquidity, positions the asset so it will appreciate in the pool’s accounting terms, waits for reimbursement eligibility, and then withdraws to claim a large reserve payout. By choosing a toxic pair, the attacker can extract value that exceeds their real economic exposure.
    
    — additional exploit (from raw "[H-02] Redemption value of synths can be manipulated to drain `VaderPool` of all native assets"): The attacker flash borrows capital, performs a large trade that makes the target asset appear very valuable, mints synthetic assets with a comparatively small deposit, reverses the trade so the target asset returns to normal or lower value, then burns the synthetic assets to withdraw more native assets than were deposited. The cycle can be repeated whenever profitable.
    
    — additional exploit (from raw "[H-32] Covering impermanent loss allows profiting off asymmetric liquidity provision at expense of reserve holdings"): The attacker adds liquidity asymmetrically, optionally performs a swap or two to move the price further, waits for reimbursement eligibility, and then removes liquidity to collect loss coverage. The reserve pays for part of the attacker-created imbalance, letting the attacker recover more value than they exposed to market risk.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Transfering funds to yourself increases your balance
  - Severity: High
  - Historical root cause: The token-transfer balance update uses a stale cached source balance and then writes both the debited source slot and the credited destination slot even when source and destination are the same account. When self-transfer is allowed, the second store overwrites the first and effectively adds the transferred amount on top of the original balance, violating conservation of balances.
  - Risk pattern: The internal balance move caches `sourceBalance` and `destBalance` separately, then stores `sourceBalance - amount` to the source slot and `destBalance + amount` to the destination slot without rejecting `source == destination`. The approval check also treats owner-as-spender as automatically approved, so the self-transfer path is reachable through the normal transfer flow.
  - Exploit shape: An attacker who already owns some LP balance calls the transfer entry point with `from = msg.sender` and `to = msg.sender`, transferring any positive amount up to the full balance. The contract first reads the pre-transfer balance, then writes back a reduced source balance and an independently incremented destination balance to the same storage slot, doubling the recorded balance for a full self-transfer. The attacker repeats the same transaction to compound the inflation before later burning or otherwise redeeming the overcredited position.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Role-gated router-administered swap execution
- Category: Dexes
- Definition: A privileged swap execution flow routes tokens through a path of constant-product pools while enforcing an authorization check before using shared protocol funds.

### Matched historical semantic: Router-Forwarded Safe Operations
- Match strength: High
- Match evidence: Both describe privileged router-based swap execution that uses protocol-held assets and enforces authorization before trading. The extract’s role-gated swap flow closely matches the historical router-forwarded safe operations with authorized execution.

#### Checklist
- [ ] Manually review this semantic; a historical semantic matched, but no linked findings were found.

## Cross-margin swap with trade registration and fee deduction
- Category: Lending
- Definition: A margin-account swap flow deducts fees, computes the routed exchange amounts, and records the trade to update borrowing and collateral obligations before executing the swap.

### Matched historical semantic: Path Quotation Across Legacy and Bin-Based Pools
- Match strength: High
- Match evidence: Both are swap-routing flows that register trade effects before execution and then use pool-routing helpers; the extract also touches fee deduction and borrow/collateral updates, which fits the router/path semantics in 334.

#### Checklist
- [ ] Check whether: [H-02] RubiconRouter: Offers created through offerForETH cannot be cancelled
  - Severity: High
  - Historical root cause: The offer-creation flow for the native-asset leg places user funds into an offer position, but there is no corresponding withdrawal or cancellation path for that position. Because the escrowed value can only leave through acceptance or cancellation and one of those exits is missing, the position can remain permanently stuck if it is never filled.
  - Risk pattern: Native-asset-to-token offer creation stores funds in an order record; the router lacks the matching cancel path for that order class; assets are only recoverable through a missing exit branch rather than a user-controlled withdrawal path.
  - Exploit shape: 1) A user opens an offer of this type. 2) The order is left unfilled. 3) The user attempts to cancel, but the router has no implementation for that cancellation path. 4) The escrowed tokens remain locked until some external fill occurs, which may never happen.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Principal-Yield AMM Swap and Liquidity Provision
- Match strength: High
- Match evidence: Both describe margin or controller-adjacent swap flows that update accounting before execution; 12 registers trade effects around routed swaps, while 725 is the principal-yield swap/liquidity market around those share tokens.

#### Checklist
- [ ] Check whether: [H-01] Steal tokens from TempusController
  - Severity: High
  - Historical root cause: A liquidity-provision path accepts an attacker-supplied integration object and trusts it to supply pool identity, token lists, balances, and minted-share outputs without validating that the integration is from an approved registry. The controller then uses those untrusted values to compute leftover amounts and transfer out ERC20 balances, so a fake integration can drive the accounting off-invariant and turn controller-held dust into transferable assets.
  - Risk pattern: The liquidity-deposit flow accepts an external integration address from the caller and derives vault/pool details from it. The code trusts external return values for pool token addresses, pool balances, and minted share amounts, then computes a remainder and transfers ERC20 tokens to msg.sender based on those values. No whitelist or registry check is applied before consuming the integration-provided data.
    
    — additional pattern (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): Deposit share minting is based on the raw amount of the input asset, and share redemption converts shares back into any requested output asset using the same nominal-unit balance model. No oracle or relative-price adjustment is applied across the accepted asset set.
    
    — additional pattern (from raw "[H-09] `removeToken` would break the vault/protocol."): The manager's token-removal flow updates the token registry without checking that vault-local balances and strategy balances for that asset are zero or migrated. Later balance and share-price code assumes the registry reflects the live asset set.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
  - Exploit shape: An attacker deploys a fake integration that returns arbitrary token addresses, fake balances, and an inflated minted-share amount. They call the deposit-and-provide-liquidity entrypoint with this fake integration. The controller reads the fabricated values, computes a positive remainder, and transfers the controller’s held ERC20 balance for the chosen token(s) to the attacker.
    
    — additional exploit (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): An attacker deposits a high-priced allowed asset while the vault's accounting credits them as if it were equal to a lower-priced asset. They then redeem their shares for the lower-priced asset or another asset in the basket. The difference between the deposit asset's real value and the withdrawal asset's real value becomes attacker profit and comes out of the pool.
    
    — additional exploit (from raw "[H-09] `removeToken` would break the vault/protocol."): An authorized operator removes an asset from a vault before migrating its live balance. The vault still holds or has deployed that asset, but the registry no longer tracks it. Subsequent withdrawals and balance queries misprice the vault and can strand the removed asset, preventing users from redeeming the true value.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Collateralized Debt Position Lifecycle
- Match strength: High
- Match evidence: Both are swap flows that register trade effects against a lending/margin account before execution, then reconcile debt repayment or new borrowing from the routed swap outcome.

#### Checklist
- [ ] Check whether: [H-02] The check for value transfer success is made after the return statement in `_withdrawFromYieldPool` of `LidoVault`
  - Severity: High
  - Historical root cause: The withdrawal routine returns from the function before verifying whether the final value transfer succeeded. This creates a broken post-condition: the accounting state assumes the withdrawal completed, but the external asset transfer may have failed and the success flag is never enforced, so the user’s claimed withdrawal can be finalized without delivering funds.
  - Risk pattern: The control flow performs an external value transfer and only afterwards contains a success require that is placed after a return statement. Because the return is hit first, the transfer-result validation never executes. The state transition that marks the withdrawal as done is therefore decoupled from actual delivery of the withdrawn value.
    
    — additional pattern (from raw "[H-04] Controller does not raise an error when there’s insufficient liquidity"): The withdrawal loop reduces the requested amount across available balance sources and exits even when a nonzero remainder is left. No final check enforces that the full requested amount was delivered before share accounting completes.
  - Exploit shape: A user calls the withdrawal function and the contract attempts to send the output asset. If the recipient-side transfer fails for any reason, the function still returns successfully because the check is unreachable. The caller’s withdrawal is considered finished on-chain even though the funds were not delivered, leaving the user with a completed withdrawal record but no payout.
    
    — additional exploit (from raw "[H-04] Controller does not raise an error when there’s insufficient liquidity"): An attacker watches for a large pending withdrawal. They front-run by withdrawing the liquid portion of the target asset from the vault and strategy, leaving insufficient liquidity. The victim's withdrawal then executes against the depleted pool, burns shares, and returns nothing or less than expected because the function does not revert on the remaining shortfall.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Wrong shortfall calculation
  - Severity: High
  - Historical root cause: The shortfall accumulator is updated by adding the newly computed shortfall to the already-updated accumulator, effectively counting the previous shortfall twice whenever an account settlement creates a deficit. The state mutation should assign the newly computed total shortfall, but instead performs an extra addition after shortfall was already derived from the prior accumulator value.
  - Risk pattern: A settlement path computes a per-account deficit from the previous global deficit plus the account’s new negative balance, then writes the per-account balance and performs a second addition into the global shortfall state. The bug is triggered whenever settlement produces a negative post-settlement balance, and the global deficit variable is incremented by a value that already embeds the old deficit.
  - Exploit shape: An attacker or normal user first creates or inherits an existing deficit in the settlement ledger, then calls the settlement path on an account that remains undercollateralized. The transaction records the old deficit plus the new deficit inside the temporary value and then adds that temporary value back into the global shortfall. Subsequent withdrawals and accounting checks read the inflated deficit, so the system reports more unrecoverable loss than actually exists until someone donates extra value to offset the doubled accounting.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Cached oracle-style peg valuation with cautious moving-average updates
- Category: Services
- Definition: A token valuation service caches a peg-denominated price estimate and updates it through bounded, path-based market observations using a weighted moving average.

### Matched historical semantic: CPI-Indexed Oracle with Time-Delayed Price Drift
- Match strength: High
- Match evidence: Both are oracle-style cached valuation systems that update a stored price from external observations under bounds and weighted averaging. The extract’s cautious moving-average peg valuation matches the historical CPI-indexed delayed drift and cache-refresh pattern.

#### Checklist
- [ ] Check whether: [H-01] Oracle price does not compound
  - Severity: High
  - Historical root cause: A time-based price accumulator is reset when a public update request rewrites the anchor timestamp before the delayed oracle callback persists the new price. Because the stored price update is computed from the freshly reset anchor rather than from the previous month-end state, the cumulative price path is lost and the oracle reverts toward its initial level instead of carrying forward prior month gains.
  - Risk pattern: A public request path resets the start anchor before the asynchronous callback updates the stored oracle price; the callback then writes oraclePrice using elapsed time measured from the new anchor rather than from the prior persisted month. The vulnerable state mutation is the combination of resetting the time origin and persisting the new price only in the delayed callback.
    
    — additional pattern (from raw "[H-02] set cap breaks vault’s Balance"): The strategy-cap update mutates the per-vault balance ledger with the wrong quantity; later withdrawal code expects the recorded vault balance and strategy balances to be internally consistent and reverts if they are not.
  - Exploit shape: An attacker waits until the feed has drifted upward, then sends the public request transaction that resets the time anchor. Before the callback arrives, the feed’s current readout drops back close to the baseline because elapsed time is near zero. When the oracle callback finally executes, it stores that near-baseline value. The attacker can then interact with any protocol path that prices collateral, minting, redemption, or accounting off the depressed oracle value.
    
    — additional exploit (from raw "[H-02] set cap breaks vault’s Balance"): An operator sets a strategy cap just below its current balance. The cap logic updates the vault ledger incorrectly. A user then submits a withdrawal that depends on the controller's balance invariant; the call reverts once the inconsistent accounting is detected, so assets remain stuck in the strategy and the user cannot complete redemption.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-03] `WrappedIbbtcEth` contract will use stalled price for mint/burn if `updatePricePerShare` wasn’t run properly
  - Severity: High
  - Historical root cause: Mint, burn, and transfer calculations trust a cached share price that is only refreshed by an external upkeep action. When that cached rate becomes stale, the contract continues to price minting and redemption against outdated state, so users can transact at a favorable stale rate and later settle against the refreshed rate for risk-free profit.
  - Risk pattern: Cached price-per-share state updated only by an external upkeep path; mint/burn/transfer conversions read the cached value without freshness validation; no max-age or staleness guard before using the cached rate in balance conversions; off-chain upkeep failure leaves pricing logic operating on outdated state.
  - Exploit shape: (1) Attacker watches the cached price update timestamp and notices it is stale relative to market movement. (2) Attacker mints while the contract still prices shares with the old cached rate. (3) After the upkeep eventually refreshes the rate, the attacker burns at the new rate. (4) The rate differential yields profit at the expense of the contract's reserves.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-04] `WrappedIbbtc` and `WrappedIbbtcEth` contracts do not filter out price feed outliers
  - Severity: High
  - Historical root cause: Mint/burn conversion logic directly consumes an externally sourced share price without any outlier rejection, smoothing, or quorum-based validation. A transient manipulated or malfunctioning price can therefore be accepted as the live valuation input, immediately skewing issuance and redemption economics.
  - Risk pattern: Direct use of externally obtained price-per-share in share conversion; no median, threshold, or deviation check before applying the price; no schedule-based commit/redeem separation; mint and burn amounts depend on the latest raw price observation.
  - Exploit shape: (1) Attacker causes or waits for a distorted external price observation. (2) The contract reads that abnormal price and uses it immediately for mint or burn conversion. (3) Attacker performs the favorable side of the conversion at the distorted rate. (4) When the price normalizes, the attacker completes the opposite leg and captures the spread from the contract or other users.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Constrained RWA Oracle Update
- Match strength: High
- Match evidence: Both are oracle-style price caches that only refresh under freshness and bounded-deviation rules, with admin-set windows and bounds. The extract’s cached peg price with weighted updates matches the historical constrained oracle update semantics.

#### Checklist
- [ ] Check whether: [H-01] `OUSGInstantManager` will allow excessive `OUSG` token minting during `USDC` depeg event
  - Severity: High
  - Historical root cause: The accounting step that computes minted output treats one unit of the payment stablecoin as one unit of fiat value regardless of market conditions, while the output asset price comes from an independent oracle with constrained updates. This creates an economic mismatch between assets entering and liabilities minted, so the protocol mints claims against more value than it actually receives when the payment asset trades below par.
  - Risk pattern: A public mint flow accepts a single stablecoin as payment; fee deduction occurs first; output amount is computed by scaling the raw token amount and dividing by an oracle price for the minted asset; there is no validation of the payment token's current market price or depeg status; the oracle for the minted asset is rate-limited and deviation-bounded, so it does not track the payment token's sudden discount.
    
    — additional pattern (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): User-controlled source address is passed directly into token transfer calls; the recipient of the minted LP tokens is also user-controlled; no access control ties the approval to the caller; approved balances are treated as if they were the caller’s funds.
  - Exploit shape: An attacker waits for the accepted stablecoin to trade below par while the receipt token oracle remains near its prior value due to bounded update rules. The attacker then calls the public mint entrypoint with a large amount of depegged stablecoin. The contract deducts fees, converts the full token amount to 18-decimal units, divides by the oracle price, and mints too many receipt tokens to the attacker. The attacker can then hold or redeem/sell the excess minted position once markets or backend settlement recognize the mismatch.
    
    — additional exploit (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): The attacker finds an account that has approved the pool, submits a mint with that account as the source, and sets themselves as the LP recipient. The pool transfers the victim’s tokens and credits the resulting liquidity position to the attacker, stealing the entire approved balance.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-04] An attacker can mint free DUSD and liquidate the corresponding Short Record to earn liquidation rewards
  - Severity: High
  - Historical root cause: The short-cancel flow can mint debt at a favorable rate while using a collateral calculation that depends on the order’s stored collateral ratio. An attacker can first reduce the short record’s collateral, then cancel the short so the protocol mints additional debt against reduced backing, pushing the resulting record below liquidation thresholds and enabling a profitable liquidation loop.
  - Risk pattern: The attack uses a collateral-reduction path on an existing short record, followed by cancellation of a short order whose remaining debt is below the minimum. The cancellation path reuses stored order parameters to derive the collateral charge, updates the short record and global debt, and then credits the shorter with the mint. If collateral has been reduced beforehand, the record’s collateral ratio after cancellation can fall below liquidation thresholds.
  - Exploit shape: 1) Attacker opens or partially fills a short so it has a live record. 2) Attacker reduces the record’s collateral through the collateral-decrease path. 3) Attacker cancels the short while the remaining debt is below the minimum, causing additional debt to be minted. 4) The resulting record is undercollateralized. 5) Attacker or a keeper liquidates the record and collects liquidation rewards.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] Protocol mints less rsETH on deposit than intended
  - Severity: High
  - Historical root cause: The receipt amount is computed after the incoming asset balance has already been added to the pool’s live balances, so the numerator of the price calculation includes the just-deposited amount and the denominator is inflated during the same transaction, reducing the minted amount below the intended pre-deposit valuation.
  - Risk pattern: Incoming assets are pulled into the pool first; the mint calculation then reads pool balances through a total-assets routine that includes the current contract balance; the receipt price is derived from current total assets divided by total supply; the final mint amount uses that inflated price inside a division.
    
    — additional pattern (from raw "[H-02] A temporary issue shows in the staking functionality which leads to the users receiving less minted tokens"): The stake flow queries adapters with full balances, one adapter flips to an expensive branch above a capacity threshold, and the same inflated price is used to mint fewer shares.
    
    — additional pattern (from raw "[H-03] Malicious Users Can Drain The Assets Of Auto Compound Vault"): Withdrawal computes shares via floor-rounded asset/share conversion, burns the previewed shares, then transfers assets; a zero-share preview makes the burn a no-op while the asset transfer still succeeds.
    
    — additional pattern (from raw "[H-02] wrong minting amount"): A mint amount variable is derived from `baseBalance * ONE / redeemRate` instead of the transfer delta; the result depends on the contract’s live balance before/after the call rather than on the user’s deposit amount; downstream issuance uses that computed value as the minted supply.
    
    — additional pattern (from raw "[H-06] the first depositor to a pool can drain all users"): First deposit sets the initial total liquidity; later share minting uses a ratio of deposited value to total liquidity; share output is integer-truncated; the attacker can inflate the effective pool value while retaining nearly all shares.
    
    — additional pattern (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): Deposit share minting is based on the raw amount of the input asset, and share redemption converts shares back into any requested output asset using the same nominal-unit balance model. No oracle or relative-price adjustment is applied across the accepted asset set.
    
    — additional pattern (from raw "[H-06] earn results in decreasing share price"): Vault-level balance aggregation sums normalized token balances from the vault itself, while controller-level balance aggregation adds only the strategy's want-side balance without applying a common price conversion. The earn path updates strategy balances using those mismatched units, so total value accounting becomes inconsistent across components.
  - Exploit shape: A user submits a normal deposit transaction. The pool first accepts the tokens, then reads its own enlarged balance to compute the receipt price, and mints a smaller receipt amount than the same deposit would have produced if priced against the pre-transfer state. Any depositor can trigger this loss simply by using the deposit path.
    
    — additional exploit (from raw "[H-02] A temporary issue shows in the staking functionality which leads to the users receiving less minted tokens"): A user deposits an amount that would be cheap in the adapter's deposit-sized branch, but because the code prices the adapter using its entire balance, the stake mints fewer shares than expected and the user is shortchanged on later unstake.
    
    — additional exploit (from raw "[H-03] Malicious Users Can Drain The Assets Of Auto Compound Vault"): Attacker seeds or acquires a tiny share balance, requests a small withdrawal that rounds burn requirement to zero, receives assets while burning no shares, and repeats until the pool is drained.
    
    — additional exploit (from raw "[H-02] wrong minting amount"): An attacker chooses a deposit timing when the contract base balance is favorable. They call the minting path with a small or manipulated deposit. Because the calculation keys off the existing balance, the attacker receives an inflated or deflated mint amount relative to the actual deposit, extracting value from the pool of token holders.
    
    — additional exploit (from raw "[H-06] the first depositor to a pool can drain all users"): An attacker makes the first deposit with the smallest possible amount, acquires nearly all shares, then increases the apparent pool value through transferable attributions. When a victim deposits a large amount, the share formula rounds down to zero, so the attacker later redeems the combined pool value.
    
    — additional exploit (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): An attacker deposits a high-priced allowed asset while the vault's accounting credits them as if it were equal to a lower-priced asset. They then redeem their shares for the lower-priced asset or another asset in the basket. The difference between the deposit asset's real value and the withdrawal asset's real value becomes attacker profit and comes out of the pool.
    
    — additional exploit (from raw "[H-06] earn results in decreasing share price"): A user deposits the base asset into the vault and waits for yield realization. Another actor triggers the earn path, which moves funds into the strategy and updates accounting in a different unit than the vault uses for its total-value calculation. After the call, the reported share price is lower than before, so all holders can redeem for less than their prior claim.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Pegged-Asset Ratio Oracle
- Match strength: High
- Match evidence: Both are cached oracle pricing services with bounded updates, path-based observations, and weighted averaging; the extract specifically describes peg valuation caching, which aligns closely with the peg-ratio oracle adapter in 345.

#### Checklist
- [ ] Check whether: [H-01] Incorrect handling of `pricefeed.decimals()`
  - Severity: High
  - Historical root cause: A ratio is normalized by multiplying by a decimal-scaling factor derived from the feed precision, but the scaling sequence assumes a single fixed precision and applies an extra exponent adjustment before truncating the result. When the feed precision differs from the expected value, the intermediate conversion produces a value with the wrong magnitude or collapses to zero, so downstream price comparisons are made against a corrupted ratio.
  - Risk pattern: A price-ratio oracle computes the lower/upper price ratio, then multiplies by a power-of-ten factor based on the first feed's decimals and divides by a fixed million-scale constant. The controller later multiplies the returned value again by another decimals-derived factor before comparing it to the strike threshold.
  - Exploit shape: An attacker or configuration mistake deploys the oracle pair using feeds whose precision is not the assumed one. The keeper then triggers the end-of-epoch or depeg path; the ratio is mis-scaled, causing the contract to take the wrong branch and finalize an incorrect settlement outcome for vault participants.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Price oracle aggregation and DEX pricing
- Match strength: High
- Match evidence: Both are cached oracle-style price services that refresh valuations from market observations under admin-controlled bounds and update windows using weighted averaging or fallback routing.

#### Checklist
- [ ] Check whether: [H-01] Rounding Issues In Certain Functions
  - Severity: High
  - Historical root cause: The vault-style conversion and preview paths rely on integer division in the share/asset conversion formula without enforcing the rounding direction required by the tokenized-vault standard. As a result, the same arithmetic can round down where the caller-facing preview is expected to round up, causing the vault to quote too few shares or too few assets for withdrawal-style flows.
  - Risk pattern: Share/asset conversion uses multiplication followed by integer division over total supply and total assets, with no explicit ceil logic for withdrawal/mint preview flows. The preview path delegates to the generic conversion path instead of applying a separate round-up branch for the burn-side quote. Any downstream consumer that assumes the preview methods satisfy the vault rounding contract can be misled.
  - Exploit shape: A caller first queries the preview method to determine how many shares or assets will be needed, then submits the corresponding deposit/withdraw transaction. Because the quote can round in the wrong direction, the actual execution can differ from the integrator’s assumed bounds, allowing a malicious or mistaken integration to proceed with an invalid price guarantee and potentially trigger loss when the quoted amount is used as a hard limit in subsequent accounting or routing logic.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-02] `UniswapV2PriceOracle.sol``currentCumulativePrices()` will revert when `priceCumulative` addition overflow
  - Severity: High
  - Historical root cause: A helper copied from an older arithmetic model relies on wraparound for the cumulative price update, but the implementation is compiled under checked arithmetic. When the cumulative accumulator or the derived increment exceeds the integer range, the addition reverts instead of wrapping, breaking the oracle update path.
  - Risk pattern: The vulnerable pattern is an external oracle helper that computes `timeElapsed` and then adds a counterfactual increment into cumulative price state without an `unchecked` block. The code assumes overflow wraparound semantics for the accumulator update, but the compiler enforces revert-on-overflow. Any call path that depends on `price0Cumulative += increment` or `price1Cumulative += increment` can fail once the values are large enough.
  - Exploit shape: 1) Allow the market to run long enough or reach sufficiently large cumulative values. 2) Call the oracle update path after the accumulator has grown near the arithmetic limit. 3) The addition overflows under checked arithmetic and reverts. 4) Any protocol action that requires a fresh oracle reading is blocked until the implementation is fixed or replaced.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-30] Newly Registered Assets Skew Consultation Results
  - Severity: High
  - Historical root cause: A newly registered pair contributes a zero-valued native-side average while still contributing a live external-price reading, so the consultation aggregate becomes biased toward the external feed until the pair has been fully updated. That makes the oracle return a skewed price during the registration window.
  - Risk pattern: Pair registration can occur before the first meaningful time-weighted update; native-side average is zero or effectively zero for the new pair; the consultation loop still includes the pair’s external-price contribution; the result is biased during the initialization window.
  - Exploit shape: An attacker registers a new asset pair and immediately triggers consultation before the pair has been updated. The oracle incorporates the fresh external price while the native-side aggregate remains zero, producing a skewed output that can be used to misprice protocol actions.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Peg liquidation and de-liquidation routing
- Category: Lending
- Definition: A collateral management flow converts a token position to peg value or back again by executing preconfigured swap routes through a router contract.

### Matched historical semantic: Constrained RWA Oracle Update
- Match strength: Medium
- Match evidence: Both provide deterministic conversion between a token position and peg/reference value using configured routes or valuation rules. The extract is route-based liquidation/de-liquidation, which is related to the historical constrained oracle and valuation machinery but not the same primitive.

#### Checklist
- [ ] Manually review this semantic; a historical semantic matched, but no linked findings were found.

## Role registry and cached access-control lookup
- Category: Services
- Definition: A role registry maintains owner-controlled permissions and main-character addresses, while consumer contracts cache these lookups for inexpensive authorization checks and service discovery.

### Matched historical semantic: Access-Controlled Deposit Allowlist and Blocklist
- Match strength: High
- Match evidence: Both are owner-managed access-control registries that cache or store who is allowed to interact with protocol functions and expose lookup helpers for downstream checks. The extract’s role registry and cached authorization lookups match the historical allowlist/blocklist governance pattern closely.

#### Checklist
- [ ] Check whether: [H-02] set cap breaks vault’s Balance
  - Severity: High
  - Historical root cause: The cap-setting path can leave the internal vault balance accounting inconsistent with reality, and later withdrawal logic depends on that accounting matching the actual strategy balance. When the mismatch is large enough, withdrawal operations hit a failing assertion or equivalent invariant check and cannot complete, trapping funds in the strategy.
  - Risk pattern: The strategy-cap update mutates the per-vault balance ledger with the wrong quantity. Later withdrawal code expects the recorded vault balance and strategy balances to be internally consistent and reverts if they are not.
  - Exploit shape: An operator sets a strategy cap just below its current balance. The cap logic updates the vault ledger incorrectly. A user then submits a withdrawal that depends on the controller's balance invariant; the call reverts once the inconsistent accounting is detected, so assets remain stuck in the strategy and the user cannot complete redemption.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-06] earn results in decreasing share price
  - Severity: High
  - Historical root cause: The vault and controller use inconsistent valuation bases for the same deposited capital: one side sums raw balances across the basket while the other side accounts only for the strategy's output-denominated balance. When earn moves funds into a strategy whose accounting unit is worth more or less than the vault's raw token basket, the total-value numerator shrinks relative to shares outstanding, causing the share price to fall after compounding instead of rise.
  - Risk pattern: Vault-level balance aggregation sums normalized token balances from the vault itself, while controller-level balance aggregation adds only the strategy's want-side balance without applying a common price conversion. The earn path updates strategy balances using those mismatched units, so total value accounting becomes inconsistent across components.
  - Exploit shape: A user deposits the base asset into the vault and waits for yield realization. Another actor triggers the earn path, which moves funds into the strategy and updates accounting in a different unit than the vault uses for its total-value calculation. After the call, the reported share price is lower than before, so all holders can redeem for less than their prior claim.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-04] Controller does not raise an error when there’s insufficient liquidity
  - Severity: High
  - Historical root cause: The withdrawal path treats a shortfall in available liquidity as a partial success instead of reverting. Because the caller still completes the share burn or withdrawal attempt while receiving less than requested, an attacker can drain readily available liquidity just before a victim transaction and force the victim into a failed or zero-return withdrawal.
  - Risk pattern: The withdrawal loop reduces the requested amount across available balance sources and exits even when a nonzero remainder is left. No final check enforces that the full requested amount was delivered before share accounting completes.
  - Exploit shape: An attacker watches for a large pending withdrawal. They front-run by withdrawing the liquid portion of the target asset from the vault and strategy, leaving insufficient liquidity. The victim's withdrawal then executes against the depleted pool, burns shares, and returns nothing or less than expected because the function does not revert on the remaining shortfall.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Compliance Registry Gating
- Match strength: High
- Match evidence: Both are registry-driven authorization layers with owner/admin-controlled role mappings and cached lookup for downstream checks. The extract’s role registry and cached access-control lookups align closely with the historical compliance registry gating pattern.

#### Checklist
- [ ] Check whether: [H-06] Borrower can drain all funds of a sanctioned lender
  - Severity: High
  - Historical root cause: The escrow creation flow passes borrower and lender/account arguments in the wrong order, so the escrow is instantiated with a mismatched identity pair. Later release checks query sanctions status against the wrong tuple, causing the escrow to appear releasable even when the actual lender remains sanctioned.
  - Risk pattern: The blocking path and withdrawal-sent-to-escrow path both call the escrow-deployment helper with the borrower and account arguments reversed relative to the helper's expected identity ordering. The escrow constructor stores those misordered parameters and uses them in its release authorization check, which consumes the wrong sanctions tuple.
  - Exploit shape: A borrower sanctions and blocks a lender, which transfers the lender's market tokens into the misconfigured escrow. The borrower then calls the escrow release path, which incorrectly treats the escrow as releasable, receives the lender's tokens, authorizes themselves as a lender, and executes withdrawals to drain the lender's share.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-08] Governance wrongly calculates `_quorumReached()`
  - Severity: High
  - Historical root cause: The quorum predicate uses only two vote buckets instead of the total voted weight. As a result, quorum is tied to the amount of opposition plus abstentions rather than total participation, which breaks the intended governance threshold and can block or distort proposal execution.
  - Risk pattern: The quorum check sums two support indexes instead of using the total votes field; proposal state stores for, against, and abstain separately; execution depends on the quorum predicate before a proposal can proceed.
    
    — additional pattern (from raw "[H-01] In `LlamaRelativeQuorum`, the governance result might be incorrect as it counts the wrong approval/disapproval"): Action creation snapshots eligible-holder counts, while vote evaluation returns holder quantity as weight; quorum compares accumulated quantity against a holder-count supply snapshot, mixing quantity and holder-count metrics.
    
    — additional pattern (from raw "[H-01] In `Governance.sol`, it might be impossible to activate a new proposal forever after failed to execute the previous active proposal."): An active proposal escrows voting balances; reclaiming votes is blocked while that proposal remains active; new proposals require fresh endorsements from the circulating supply; there is no forced-reset or expiry path for an unexecutable active proposal.
  - Exploit shape: (voters, cast mostly support votes) -> total participation is high but against+abstain remains low -> quorum check fails incorrectly and governance stalls; alternatively, concentrated opposition/abstention can satisfy the predicate even if total participation is otherwise inadequate.
    
    — additional exploit (from raw "[H-01] In `LlamaRelativeQuorum`, the governance result might be incorrect as it counts the wrong approval/disapproval"): A holder with multiple quantity units can approve or disapprove an action with fewer distinct voters than intended, causing premature pass/fail decisions.
    
    — additional exploit (from raw "[H-01] In `Governance.sol`, it might be impossible to activate a new proposal forever after failed to execute the previous active proposal."): An attacker or unlucky proposer gets a proposal activated, but it cannot satisfy execution. Because the active proposal cannot be cleared and votes remain escrowed, circulating voting power shrinks below the endorsement threshold for any successor proposal, permanently stalling governance.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-07] `_voteSucceeded()` returns true when `againstVotes > forVotes` and vice versa
  - Severity: High
  - Historical root cause: The proposal-success predicate compares the wrong vote buckets: it treats the against tally as the approval tally and the approval tally as the rejection tally. This inverts governance outcomes, so proposals that should pass can fail and proposals that should fail can execute.
  - Risk pattern: Proposal vote tallies are stored by support index, but the success predicate compares the index assigned to opposition against the index assigned to support; proposal execution depends on that predicate; the public proposal view exposes the opposite mapping for for/against vote counts.
  - Exploit shape: (voters, cast votes, support majority) -> success check reads the against bucket instead of the for bucket -> the proposal is rejected despite majority support; conversely, a proposal with majority opposition is marked successful and can proceed to execution.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Shared Administrator Access Control
- Match strength: High
- Match evidence: Both are authorization registries used by downstream contracts for inexpensive role and endpoint lookup; the extract caches service roles and addresses, while 338 is a shared admin access-control layer.

#### Checklist
- [ ] Check whether: [H-01] Owner can not set the `ve` address via `RewardDistributor.addVoteEscrow`
  - Severity: High
  - Historical root cause: The initial vote-escrow binding path ignores the caller-supplied address and assigns the live pointer from an uninitialized pending slot instead. As a result, the privileged setup step writes a zero address into the reward-routing dependency, leaving the reward distributor unable to recognize any staking NFT holder as eligible.
  - Risk pattern: Owner-only initialization branch checks whether the live vote-escrow pointer is unset, but the assignment uses a separate storage variable that has not been initialized. Subsequent claim logic requires the dependency pointer to be nonzero before any claims can succeed.
  - Exploit shape: A privileged deployer calls the registration step with a valid vote-escrow address. The contract enters the first-time branch, but writes zero instead of the supplied address. Thereafter any user calling the reward-claim path hits the nonzero-address gate and the reward system remains unusable until the state is corrected.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-05] Missing Complication check in `takeMultipleOneOrders`
  - Severity: High
  - Historical root cause: The multi-order taker path skips the per-order execution-policy check that is used by the other matching paths. Because maker orders can encode restrictions in their execution-policy layer, omitting that validation lets an arbitrary caller satisfy orders that were meant to be gated by custom rules.
  - Risk pattern: The batch one-order-taking path validates signature and pricing but omits the complication-specific execution predicate; maker-side policy is therefore not consulted before settlement; the path still updates nonce and transfers assets/funds as if the policy had approved the fill.
  - Exploit shape: A seller creates an order whose custom execution policy only allows a chosen counterparty. An arbitrary third party submits that order through the batch one-order-taking route instead of the restricted route. Because the missing policy check never runs, the order is settled and the unauthorized caller acquires the assets.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] `Minter.sol#startInflation()` can be bypassed.
  - Severity: High
  - Historical root cause: The inflation scheduler is treated as uninitialized by relying on zero-valued timestamp state, but the permissionless rate-update path reads and mutates those timestamps before governance has explicitly started emissions. Because the update logic does not gate on the initialization marker, any caller can force the contract into an initialized-looking state and bypass the intended governance-only start step.
  - Risk pattern: A public update path reads zero-initialized timestamp state directly; the start function is the only place that sets the emission timestamps; the update path lacks a `lastEvent != 0` / `lastInflationDecay != 0` precondition; subsequent mint and availability accounting consume `lastEvent`, `lastInflationDecay`, and the derived totals.
  - Exploit shape: An arbitrary caller watches deployment, then submits the public update call before governance submits the start call. The update observes zero timestamps, advances the emission schedule, and mutates the tracked totals. Afterwards, governance’s intended start sequencing is no longer enforceable because the emission state has already been initialized through the public path.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Protocol Governance Administration
- Match strength: High
- Match evidence: Both are access-control registries for protocol roles and service discovery, with owner/governance-controlled updates and cached lookup patterns for downstream authorization checks.

#### Checklist
- [ ] Check whether: [H-01] If a gauge that a user has voted for gets removed, their voting power allocated for that gauge will be lost
  - Severity: High
  - Historical root cause: The accounting model stores user voting-power consumption per target and requires a later write against the same target to release that consumption. A registration check is applied before the release logic, so once governance deletes the target from registry state, users lose the only state transition that can burn down their historical allocation. This creates a permanent mismatch between registry validity and user power accounting.
  - Risk pattern: The vote-update entrypoint validates that the target is still registered before processing any update, while used-power accounting also depends on historical per-user per-target allocations. Removal clears target registration state, and the code path for setting weight to zero is not exempted from the registration check. As a result, `vote user slopes` / used-power state can remain nonzero after target deletion with no reachable path to decrement it.
    
    — additional pattern (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): The burn path overwrites the pending decision struct with default values; the withdrawal check relies on the unlock timestamp inside that struct; the code does not isolate one burned lock from later locks for the same participant in a way that preserves ownership separation.
    
    — additional pattern (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): The resume function checks only per-pool pause state; it does not inspect the caller or require an owner/operator role; it flips the shared locked flag to false once checks pass.
    
    — additional pattern (from raw "[H-13] Council veto protection does not work"): The veto routine checks proposal calldata content for a selector-like value, but the proposal structure stores the selector separately from the argument payload, so the protected action is never matched correctly.
    
    — additional pattern (from raw "[H-11] (dex-v1) BasePool.mint() function can be frontrun"): Asset transfer and mint are separated; mint has no binding proof that the caller was the party that supplied the assets; the NFT owner is assigned based on transaction order; the pool accepts direct minting without router enforcement.
    
    — additional pattern (from raw "[H-19] Governance veto can be bypassed"): Veto eligibility is checked against the proposal’s action destinations; actions directed at governance are treated as non-vetoable; the proposal creator controls the action list; adding a no-op governance action changes veto behavior.
  - Exploit shape: A user locks value and allocates 100% of their voting power to one reward target. Later, governance removes that target from the approved set. The same user then tries to allocate weight to another target, but the system still counts the old allocation as used power and reverts. The user also cannot submit a zero-weight update for the removed target because the validation path rejects removed targets, so the spent power remains stuck indefinitely.
    
    — additional exploit (from raw "[H-04] Logic error in `burnFlashGovernanceAsset` can cause locked assets to be stolen"): An attacker creates a malicious pending lock and has it burned. Another user later creates a fresh pending lock. Because the attacker’s record was reset rather than removed, the attacker’s withdrawal call passes the unlock-time check and pulls the later user’s locked assets.
    
    — additional exploit (from raw "[H-12] `IndexTemplate.sol` Wrong implementation allows lp of the index pool to resume a locked `PayingOut` pool and escape the responsibility for the compensation"): An LP waits until the external pool states satisfy the pause check, calls resume from their own account, and clears the shared lock before compensation accounting is finalized.
    
    — additional exploit (from raw "[H-13] Council veto protection does not work"): Governance proposes council replacement; the sitting council calls veto, but the check reads the wrong bytes and fails to identify the protected action, leaving the council in place.
    
    — additional exploit (from raw "[H-11] (dex-v1) BasePool.mint() function can be frontrun"): The victim deposits pool assets and sends a mint transaction. An attacker watches for the balance increase or pending mint, front-runs the transaction, calls mint first, receives the NFT representing the deposit, and later burns it to withdraw the underlying assets.
    
    — additional exploit (from raw "[H-19] Governance veto can be bypassed"): The attacker submits a malicious proposal and includes an additional action that points to governance but does nothing meaningful. When the council tries to veto, the presence of that action prevents the veto from applying, allowing the malicious proposal to continue.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Design flaw and mismanagement in vault licensing leads to double counting in collateral ratios and positions collateralized entirely with kerosine
  - Severity: High
  - Historical root cause: The collateral registry is reused for two distinct purposes: eligibility/licensing and price-accounting. As a result, the same collateral source can be registered in both the exogenous-collateral set and the endogenous-collateral set, so collateral value is counted twice in collateral-ratio calculations. Separately, an endogenous collateral source can be registered as ordinary collateral, so positions can satisfy minting and liquidation checks with a large share of endogenous value rather than the intended exogenous backing.
  - Risk pattern: A shared licensing/whitelisting mapping is consumed by both collateral-ratio accounting and endogenous-asset pricing. The same asset address can be added to both the ordinary-collateral set and the endogenous-collateral set for a given position, and the collateral-ratio function sums both sets without deduplicating overlap. Separate registration paths do not enforce mutual exclusivity between the two sets.
    
    — additional pattern (from raw "[H-02] `VaderPoolV2` owner can steal all user assets which are approved `VaderPoolV2`"): A privileged entry point accepts a caller-supplied funding/source address and uses it in transferFrom without requiring it to match the caller or another authenticated owner field; approved allowances on that source can be consumed by the privileged caller.
    
    — additional pattern (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): The contract maintains one native-side reserve balance for both synthetic issuance backing and ordinary LP liquidity; LP mint/burn calculations read the same aggregate reserve, so withdrawals can redeem against synth-backed value.
    
    — additional pattern (from raw "[H-01] `VaderPoolV2` minting synths & fungibles can be frontrun"): A mint/deposit function accepts an arbitrary source address and immediately calls transferFrom(source, address(this), amount) before binding the output to the authenticated depositor; the source is not derived from msg.sender.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
    
    — additional pattern (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): User-controlled source address is passed directly into token transfer calls; the recipient of the minted LP tokens is also user-controlled; no access control ties the approval to the caller; approved balances are treated as if they were the caller’s funds.
    
    — additional pattern (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): Different liquidity representations coexist without a unified ownership ledger; synth-minted liquidity is not counted when normal LP shares are burned; withdrawal logic can drain all assets even though synth claims remain outstanding.
    
    — additional pattern (from raw "[H-23] Synth tokens can get over-minted"): Minted synthetic supply increases while the corresponding reserve side remains freely available; collateral backing is not locked or deducted; later liquidity removal can empty the pool while synth supply still exists.
    
    — additional pattern (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The mint function trusts user-controlled `from` and `to` parameters; token transfer uses the provided source address rather than binding to the caller; minted output is sent to an arbitrary recipient; there is no authorization check tying the source to the spender.
    
    — additional pattern (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): Caller controls the source account used for both token transfers; caller controls the recipient of minted LP tokens; the function lacks a spender-owner relationship check; the output position is minted based solely on supplied parameters.
    
    — additional pattern (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): Deposit share minting is based on the raw amount of the input asset, and share redemption converts shares back into any requested output asset using the same nominal-unit balance model. No oracle or relative-price adjustment is applied across the accepted asset set.
    
    — additional pattern (from raw "[H-06] earn results in decreasing share price"): Vault-level balance aggregation sums normalized token balances from the vault itself, while controller-level balance aggregation adds only the strategy's want-side balance without applying a common price conversion. The earn path updates strategy balances using those mismatched units, so total value accounting becomes inconsistent across components.
    
    — additional pattern (from raw "[H-09] `removeToken` would break the vault/protocol."): The manager's token-removal flow updates the token registry without checking that vault-local balances and strategy balances for that asset are zero or migrated. Later balance and share-price code assumes the registry reflects the live asset set.
    
    — additional pattern (from raw "[H-10] An attacker can steal funds from multi-token vaults"): The total-balance function sums normalized balances across all accepted assets, and share redemption uses that total as though each token were a fungible unit of value. No price oracle, peg check, or virtual-price adjustment is applied before minting or redeeming shares.
  - Exploit shape: An attacker opens a position, registers the same collateral source in both tracking sets, deposits once, and then mints debt against the inflated ratio so the account appears healthier than it is. Alternatively, the attacker registers an endogenous collateral source in the ordinary-collateral set, deposits that asset, and mints debt as if the position were sufficiently backed by exogenous collateral, even though the backing is primarily endogenous.
    
    — additional exploit (from raw "[H-02] `VaderPoolV2` owner can steal all user assets which are approved `VaderPoolV2`"): An owner invokes pair-support setup with a victim-approved wallet as funding source, causing the pool to transfer the victim's approved tokens into the pool and assign the resulting position to an attacker-controlled recipient.
    
    — additional exploit (from raw "[H-12] Using single total native reserve variable for synth and non-synth reserves of `VaderPoolV2` can lead to losses for synth holders"): A synth minter deposits native assets to back a synthetic position; a later LP burn redeems from the merged reserve, consuming the synth-backed portion; the synth minter later receives less native value than originally contributed.
    
    — additional exploit (from raw "[H-01] `VaderPoolV2` minting synths & fungibles can be frontrun"): A pending mint is copied by an attacker who keeps the victim as the source but substitutes an attacker-controlled recipient, causing the victim’s approved assets to be transferred and the minted position to be credited to the attacker.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
    
    — additional exploit (from raw "[H-26] All user assets which are approved to VaderPoolV2 may be stolen"): The attacker finds an account that has approved the pool, submits a mint with that account as the source, and sets themselves as the LP recipient. The pool transfers the victim’s tokens and credits the resulting liquidity position to the attacker, stealing the entire approved balance.
    
    — additional exploit (from raw "[H-33] Mixing different types of LP shares can lead to losses for Synth holders"): A user mints synth exposure, another liquidity provider withdraws the normal LP position that controls the actual pool shares, and the pool is emptied before the synth holder can redeem. The synth holder is left with a claim against an asset pool that no longer contains sufficient backing.
    
    — additional exploit (from raw "[H-23] Synth tokens can get over-minted"): An attacker mints synths while the pool is thinly collateralized, then withdraws the liquidity that was implicitly backing those synths. The synths remain outstanding but are no longer backed by recoverable assets, and the attacker can later wait for new liquidity to arrive and redeem against it.
    
    — additional exploit (from raw "[H-13] Anyone Can Arbitrarily Mint Synthetic Assets In `VaderPoolV2.mintSynth()`"): The attacker monitors approvals, then submits a mint transaction that names the victim as the source and the attacker as the recipient. The pool transfers the victim’s approved tokens, mints the synthetic asset, and sends the output to the attacker before the victim can react.
    
    — additional exploit (from raw "[H-14] Anyone Can Arbitrarily Mint Fungible Tokens In `VaderPoolV2.mintFungible()`"): The attacker watches for token approvals to the pool, then submits a liquidity mint with the victim as source and the attacker as recipient. The contract transfers the victim’s assets, mints LP units, and assigns them to the attacker, stealing the victim’s approved balance.
    
    — additional exploit (from raw "[H-05] Vault treats all tokens exactly the same that creates (huge) arbitrage opportunities."): An attacker deposits a high-priced allowed asset while the vault's accounting credits them as if it were equal to a lower-priced asset. They then redeem their shares for the lower-priced asset or another asset in the basket. The difference between the deposit asset's real value and the withdrawal asset's real value becomes attacker profit and comes out of the pool.
    
    — additional exploit (from raw "[H-06] earn results in decreasing share price"): A user deposits the base asset into the vault and waits for yield realization. Another actor triggers the earn path, which moves funds into the strategy and updates accounting in a different unit than the vault uses for its total-value calculation. After the call, the reported share price is lower than before, so all holders can redeem for less than their prior claim.
    
    — additional exploit (from raw "[H-09] `removeToken` would break the vault/protocol."): An authorized operator removes an asset from a vault before migrating its live balance. The vault still holds or has deployed that asset, but the registry no longer tracks it. Subsequent withdrawals and balance queries misprice the vault and can strand the removed asset, preventing users from redeeming the true value.
    
    — additional exploit (from raw "[H-10] An attacker can steal funds from multi-token vaults"): An attacker deposits a cheaper asset into the vault while it holds a basket of more expensive assets. They then redeem shares for the expensive assets. Since the vault treats all balances as equal units, the attacker receives a basket with higher market value than their deposit, and the difference is lost by other depositors.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] The distribution logic will be broken after calling `rageQuit()`
  - Severity: High
  - Historical root cause: The distribution calculator derives each holder's entitlement from the live total voting power at claim time, instead of snapshotting the total supply used by the already-created distribution. When some holders burn their positions before all claims are made, the denominator shrinks and the remaining unclaimed balance is repartitioned across the surviving positions, so later claims read a corrupted share basis.
  - Risk pattern: A claim path computes entitlement from `votingPowerByTokenId[tokenId] / _governanceValues.totalVotingPower` at claim time. The total voting power is mutable after distribution funding because the burn/rage-quit path reduces `totalVotingPower` and `mintedVotingPower`. Distribution state does not store the total supply snapshot for each distribution batch, so later claims observe post-burn governance state rather than the state at distribution creation.
    
    — additional pattern (from raw "[H-01] first user can steal everyone else’s tokens"): Share issuance derives from live vault balance rather than only freshly deposited principal; direct transfers to the vault are indistinguishable from user deposits in the mint calculation; minimal seed deposits allow an attacker to keep first-share ownership while manipulating the denominator for later mints.
    
    — additional pattern (from raw "[H-13] Admin of the index pool can `withdrawCredit()` after `applyCover()` to avoid taking loss for the compensation paid for a certain pool"): Credit withdrawal remains open after cover application; compensation is computed later during the payout/resume flow; the credited balance used for loss sharing can be reduced to zero between those steps.
    
    — additional pattern (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): Collateral-send path calls unwrap before reward update; user reward state remains stale at the moment the wrapped collateral is burned/removed; later reward claims can still read the pre-withdrawal balance and pay out yield on exited collateral.
    
    — additional pattern (from raw "[WH-02] WJLP will continue accruing rewards after user has unwrapped his tokens"): Unwrap path burns wrapped balance and withdraws underlying collateral, but does not reduce the user’s tracked stake in the reward ledger; reward accrual logic continues to read the old amount when computing unclaimed rewards.
  - Exploit shape: An attacker who owns multiple positions waits until a distribution is funded, then claims with one position while the current total voting power still reflects all positions. Next, the attacker burns that claimed position via the rage-quit path, which lowers the live total voting power. Finally, the attacker claims with the remaining position(s); because the denominator is now smaller, the claim formula returns a larger fraction for those remaining positions, allowing the attacker to collect more than their original pro-rata share and leaving other holders underpaid.
    
    — additional exploit (from raw "[H-01] first user can steal everyone else’s tokens"): (1) Attacker makes the minimum initial deposit and receives the first share. (2) Attacker donates extra tokens directly to the vault address. (3) Victim stakes normally, but the mint formula sees an inflated balance and rounds their shares down to zero or too few. (4) Attacker redeems and receives the victim’s deposit plus the donated tokens.
    
    — additional exploit (from raw "[H-13] Admin of the index pool can `withdrawCredit()` after `applyCover()` to avoid taking loss for the compensation paid for a certain pool"): A participant waits until a pool has entered an incident-covered period and premium has accrued, withdraws credit before compensation executes, and thereby escapes future loss sharing while other LPs absorb a larger share.
    
    — additional exploit (from raw "[WH-05] ActivePool unwraps but does not update user state in WJLP"): A collateral manager unwraps a user’s wrapped position and only later updates rewards; because the reward ledger reads the post-burn state, the user can either lose accrued yield or keep claiming against stale stake, depending on the direction of the accounting error.
    
    — additional exploit (from raw "[WH-02] WJLP will continue accruing rewards after user has unwrapped his tokens"): A user wraps collateral, accrues rewards, then unwraps. Because the unwrap does not decrement the tracked stake, subsequent claims still use the old balance and pay rewards that should have stopped accruing.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

## Constant-product path pricing utilities
- Category: Dexes
- Definition: A pricing library computes chained swap quotes and required inputs across a sequence of constant-product pools using sorted token orientation and reserve reads.

### Matched historical semantic: Local stable-swap liquidity pool
- Match strength: High
- Match evidence: Both are constant-product AMM quote engines that compute chained swap amounts across ordered token paths using reserves, fees, and hop-by-hop routing math.

#### Checklist
- [ ] Check whether: [H-02] Wrong implementation of `withdrawAdminFees()` can cause the `adminFees` to be charged multiple times and therefore cause users’ fund loss
  - Severity: High
  - Historical root cause: Fee balances are read from a storage array and transferred out, but the corresponding storage entries are never zeroed after withdrawal. Because the accounting source of truth remains unchanged, the same fee balance can be withdrawn repeatedly on subsequent calls.
  - Risk pattern: Loop over pooled assets reads fee amounts from a storage array and performs token transfers without mutating the stored fee balances; no post-transfer reset of the per-asset fee accounting entries; repeated calls observe the same nonzero accounting state and transfer again.
  - Exploit shape: A privileged caller invokes the fee withdrawal path once to collect the accrued fees, then calls it again later after any new accrual or even immediately. Because the fee ledger was never cleared, the contract transfers the same amounts again, progressively draining pool value that should have remained reserved for liquidity providers.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Two-Asset Liquidity Provision and Redemption
- Match strength: High
- Match evidence: Both are AMM path-pricing utilities that compute chained quotes across multi-hop constant-product pools using sorted token orientation and reserve reads.

#### Checklist
- [ ] Check whether: [H-01] Malicious users can provide liquidity on behalf of others to keep others in the liquidity cooldown
  - Severity: High
  - Historical root cause: The liquidity-adding path accepts an arbitrary recipient of the new position and uses that recipient’s position timestamp as the cooldown anchor, but it does not require the caller to be the same party that will later be restricted. As a result, an unrelated actor can refresh another account’s cooldown timestamp by making even a tiny additive liquidity change to that account’s position.
  - Risk pattern: The minting flow takes separate sender and recipient inputs, updates position state for the recipient, and stores the current block time as that position’s last-liquidity-add timestamp whenever liquidity increases. The later burning flow checks the stored timestamp and reverts if the elapsed time is below the configured cooldown. There is no binding between the caller and the recipient of the position update, so any caller can advance another account’s cooldown state.
  - Exploit shape: An attacker observes a target position that is subject to cooldown. The attacker then submits one or more mint transactions with themselves as the caller but the victim as the recipient, adding minimal liquidity each time. Each successful mint resets the victim’s cooldown timestamp to the current block time. When the victim later submits a burn transaction, it reverts until the attacker stops refreshing the timestamp and the full cooldown period elapses, effectively preventing withdrawal during the attack window.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-01] Reliance on `lifiData.receivingAssetId` can cause loss of funds
  - Severity: High
  - Historical root cause: The post-swap payout step reads the destination asset from a separate metadata field instead of deriving it from the executed swap path, so the contract computes the recipient balance and performs the final transfer for an asset that may not match the asset actually received by the last swap. This breaks the accounting invariant that the asset used for post-swap settlement must equal the asset produced by the swap sequence.
  - Risk pattern: The swap executor updates balances using one asset identifier for the outer payout while the inner swap loop may produce a different final asset. The vulnerability is triggered when the metadata asset field used for settlement diverges from the last swap leg’s receiving asset. The final transfer uses the tracked balance delta of the metadata asset rather than the asset actually received from the swap chain.
  - Exploit shape: (1) User submits a swap bundle where the last swap leg outputs a different token than the metadata receiving-asset field. (2) The router executes the swaps and acquires the output token. (3) Settlement measures and transfers only the metadata asset balance, which is unchanged. (4) The real output token remains trapped in the contract balance, so the user receives nothing and must recover funds through an off-path manual intervention, if any exists.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase

### Matched historical semantic: Pricing Function and LP Supply Math Adapter
- Match strength: High
- Match evidence: Both are constant-product path pricing utilities that compute chained swap quotes and required inputs across multi-hop pools using reserve reads.

#### Checklist
- [ ] Check whether: [H-03] Wrong implementation of function `LBPair.setFeeParameter` can break the funcionality of LBPair and make user’s tokens locked
  - Severity: High
  - Historical root cause: The packed-fee updater reconstructs a storage word from two bitfields but forgets to shift the preserved upper field back into its high-bit position before OR-ing the values together. This corrupts both the static fee configuration and the variable-fee state in the same slot, leaving the pair with nonsensical parameters that can make core actions revert.
  - Risk pattern: The setter reads the existing fee slot, extracts the high-bit variable section, extracts the low-bit static section from the incoming packed bytes, and then writes `or(newSection, oldSection)` back to storage instead of `or(newSection, shl(144, oldSection))`. Because the preserved data is not shifted to its intended bit range, unrelated fields overlap and the packed struct becomes invalid.
  - Exploit shape: An admin or privileged updater calls the fee-parameter update path after the pool has accrued nonzero variable-fee state. The contract stores the merged word without shifting the retained bits, causing the configured bin step and variable-fee fields to become corrupted. Subsequent user actions that depend on valid fee parameters start reverting, effectively locking liquidity and preventing normal pool operation.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
- [ ] Check whether: [H-05] Attacker can steal entire reserves by abusing fee calculation
  - Severity: High
  - Historical root cause: The fee-accrual bookkeeping skips updates for transfers involving the pool address, allowing newly minted liquidity positions held by that address to retain a zero debt baseline. Combined with an unchecked subtraction path when collecting fees, an attacker can repeatedly inflate fee totals and convert the accounting mismatch into reserve theft.
  - Risk pattern: The token-transfer hook short-circuits fee caching when either endpoint is the pool address, so the pool’s own balances are not initialized against the current accumulated-per-share values. Later, fee collection subtracts amounts from global fee totals inside an unchecked block, which allows the totals to overflow or diverge instead of reverting on inconsistent accounting. Swap and collect paths then trust those totals when computing distributable amounts.
    
    — additional pattern (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): Withdrawal compensation uses the instantaneous reserve ratio / spot price as the loss reference; the LP can trade against the pool before burn; compensation is paid from a shared reserve; the attacker can restore the pool after collecting the payout.
  - Exploit shape: An attacker sends underlying tokens to the pool, mints liquidity to the pool address, and calls the fee-collection path using the pool as the account. Because the hook never cached fees for that address, the pool’s debt baseline is wrong and the collection path mutates global fee totals without a safety check. The attacker then triggers a swap using the inflated fee state to extract reserve assets, and finally burns the minted position to recover the original principal.
    
    — additional exploit (from raw "[H-05] LPs of VaderPoolV2 can manipulate pool reserves to extract funds from the reserve."): The attacker provides liquidity, waits until reimbursement has accrued, flash borrows one side of the pair, trades to heavily skew the pool, burns liquidity while the skew makes the loss calculation large, receives reserve compensation, then trades back to restore the pool. The attacker keeps the compensation while largely preserving the underlying LP position.
  - KG link strength: High
  - KG evidence: in-project link: finding and semantic co-emitted by the extract pipeline against the same project; finding instantiates the semantic in its originating codebase
