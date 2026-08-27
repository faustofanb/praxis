# Code Quality Rules

- TypeScript strict; no `any` except isolated third-party boundary shims.
- Use `unknown` + schema validation at untrusted boundaries.
- Prefer discriminated unions over boolean flag combinations.
- No TypeScript enums/namespaces.
- Pure reducers and parsers stay side-effect-free.
- Exceptions are for exceptional control flow; expected runtime outcomes use typed results/unions.
- Do not silently catch errors. Either classify, record, translate, or rethrow.
- Do not create generic abstractions until at least two concrete uses demonstrate the shared concept.
- Keep functions cohesive. Split by responsibility, not arbitrary line count.
- Comments explain invariants, failure semantics, or non-obvious reasons.
- Generated data must have a generator/source of truth; do not hand-edit generated outputs.
- Exact dependency versions only.
