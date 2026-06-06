# Vault Rewards Example

A small Solidity project for exercising Learn KG on a concrete protocol shape.

The project contains:

- user deposits and withdrawals;
- share accounting;
- reward accrual based on `block.timestamp`;
- owner-configurable reward rate;
- an intentionally simple implementation that keeps the source readable for local runs.

Run it with:

```bash
learnkg learn-projects \
  --db sqlite:///kg.sqlite3 \
  --project "vault_rewards:examples/simple_project" \
  --report vault_rewards:examples/simple_project/audit.md \
  --link
```
