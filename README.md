# Praxis V2

Praxis V2 is a clean-room workflow kernel for bounded AI-assisted business development.

This branch intentionally contains no V1 runtime, profile, capability, extension, rule, migration layer, or command shim. Worktrunk is the only worktree implementation. The architecture and acceptance contract live in [docs/praxis-v2-blueprint.md](docs/praxis-v2-blueprint.md).

```bash
mise install
mise run setup
mise run verify
uv run praxis version --json
```

