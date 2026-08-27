# Dependency Rules

Before adding a dependency:

1. Name the current concrete problem.
2. Check Bun/TypeScript/standard library support.
3. Check maintenance and license.
4. Check dependency count and native/runtime impact.
5. Decide whether it belongs in Core or Adapter.
6. State failure behavior and security implications.
7. Pin an exact version.
8. Add/update tests and lockfile.

Never upgrade unrelated dependencies in a feature/fix task.

Core dependency additions normally require an ADR.
