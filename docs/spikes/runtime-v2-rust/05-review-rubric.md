# Architecture Review Rubric

Weighted decision evidence:

| Dimension | Weight |
|---|---:|
| Semantic correctness | 20 |
| Authority/state clarity | 15 |
| Failure/recovery clarity | 10 |
| OSS reuse potential | 15 |
| Ecosystem/community maturity | 10 |
| Maintainer auditability | 15 |
| Performance/resource behavior | 10 |
| TS↔Rust integration cost | 5 |

Each side receives 0–5 per dimension with concrete evidence.

Hard gates dominate weighted score. A hard-gate failure cannot be hidden by benchmark performance or subjective elegance.

Code review must report at least:

- comparable LOC
- domain type count
- cross-language message count
- duplicated concepts/state count
- non-test `unsafe` count
- non-test `unwrap/expect` count
- largest coordinator/function size
- number of places that can write authoritative state
