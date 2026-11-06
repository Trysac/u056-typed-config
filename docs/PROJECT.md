# Project record

## Objective

Typed configuration from environment, .env and JSON files into frozen dataclasses, with aggregated errors, masked secrets and generated docs

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: anything that needs runtime dependencies or I/O without an accepted ADR.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 494561 / 124738 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.9935 |

## Factory run u056 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2308 | 110457 | 0 | 4246 | 0.5550 |
| fix-1 | claude-sonnet-5-5 | no | 6 | 481 | 5746 | 39401 | 0.0231 |
| fix-2 | claude-sonnet-5-5 | no | 8 | 2161 | 21155 | 68002 | 0.0813 |
| fix-3 | claude-sonnet-5-5 | no | 6 | 892 | 7222 | 41660 | 0.0312 |
| fix-4 | claude-sonnet-5-5 | no | 8 | 979 | 6994 | 55500 | 0.0328 |
| audit | claude-sonnet-5-5 | no | 12 | 5678 | 48427 | 149459 | 0.1928 |
| docs | claude-haiku-5-5 | no | 133945 | 4090 | 0 | 0 | 0.0772 |

Total: $0.9935. Prices: Anthropic list prices.
