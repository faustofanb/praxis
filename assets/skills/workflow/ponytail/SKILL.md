---
name: ponytail
description: Prefer the smallest correct implementation using YAGNI, standard-library and native-platform features before dependencies or abstractions. Use for implementation, refactoring, simplification, or reviews that ask about over-engineering, unnecessary code, dependencies, or speculative flexibility.
---

# Ponytail

1. Confirm the requested behavior and the smallest observable success criteria.
2. Delete unnecessary work before adding code. Prefer existing code, the standard library, and native platform features.
3. Avoid speculative layers, configuration, dependencies, and generalization. State any shortcut that creates real follow-up debt.
4. Preserve correctness, security, user data, and required verification; minimal does not mean incomplete.
5. End with the smallest focused test or check that proves the behavior.

Praxis may emit `PONYTAIL_DIFF_GROWTH` as a non-blocking prompt to reconsider a growing diff. Treat it as review guidance, never as a delivery gate.
