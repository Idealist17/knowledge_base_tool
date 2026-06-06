# Vault Rewards Review

## Scope

The review covers `src/Vault.sol`, a timestamp-based staking vault with ETH deposits, withdrawals, reward accrual, and owner-managed reward rate configuration.

## Finding: Reward rate changes are applied without settling user rewards first

Severity: Medium

The owner can change `rewardRatePerSecond` while users already have balances. The contract does not force a global or per-user settlement before the new rate is used. A user that delays interaction can have rewards calculated across a time window using a rate that was not active for the full period.

Affected behavior:

- `setRewardRate(uint256 newRate)` changes the rate immediately.
- `_accrued(address user)` multiplies the entire elapsed time by the current `rewardRatePerSecond`.
- `claim()` and `withdraw(uint256 amount)` depend on `_accrued`.

Recommendation: checkpoint rewards before rate changes, or store reward index history so accrual uses the correct rate for each time interval.

## Finding: Timestamp-based reward calculation is sensitive to block time manipulation

Severity: Low

Rewards are calculated directly from `block.timestamp`. Miners or validators have limited control over timestamps, which can slightly alter reward amounts around claims or withdrawals.

Recommendation: use timestamp-based rewards only when small timing variance is acceptable, cap maximum accrual intervals, or move to epoch-based accounting.
