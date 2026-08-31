# Benchmark Specification

Benchmark is comparative evidence, not the sole migration gate.

Measure on the same machine / commit / fixture generator:

- 1k event replay/projection
- 10k event replay/projection
- 100k event replay/projection
- SQLite reopen/recovery time
- observed peak RSS where feasible
- process startup / runner startup
- fixture throughput

Record:

- OS / architecture
- CPU / memory summary
- Rust toolchain
- Bun version
- reference commit
- candidate commit
- warmup/repetition method
- raw samples and summary

Do not cherry-pick only favorable metrics. Report regressions.
