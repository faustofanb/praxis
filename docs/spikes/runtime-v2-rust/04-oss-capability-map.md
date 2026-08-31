# OSS Capability Map — Spike Working Record

This file is intentionally dynamic during the Spike.

Before adding a Rust dependency, record:

| Capability | Candidate | Exact version | Maintenance/recent release | Community | License | Security/failure impact | Replaceability | Code saved | Decision |
|---|---|---:|---|---|---|---|---|---|---|
| serialization | serde | TBD exact lock | evaluate at add time | mature | verify | low/medium | high | high | candidate |
| JSON | serde_json | TBD exact lock | evaluate | mature | verify | low | high | high | candidate |
| typed errors | thiserror | TBD exact lock | evaluate | mature | verify | low | high | medium | candidate |
| SQLite | rusqlite | TBD exact lock | evaluate | mature | verify | high | medium | high | candidate |
| temp fixtures | tempfile | TBD exact lock | evaluate | mature | verify | low | high | medium | candidate |

Rules:

- Rust toolchain is pinned to 1.98.0 for the Spike unless a concrete incompatibility is proven.
- Add Tokio only if actual async/concurrency evidence requires it; the deterministic kernel must not become async merely by default.
- Do not outsource Praxis domain state/transition semantics to a generic state-machine library.
- Exact crate pins are captured by `Cargo.lock`; any explicit manifest dependency constraint should remain narrow and reviewed.
