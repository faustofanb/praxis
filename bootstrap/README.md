# Bootstrap Config

These files are **templates for M0 repository initialization**, not a promise that the repository already exists.

Suggested sequence after creating the real repository:

1. Copy these files to repository root.
2. Install mise and run `mise install`.
3. Run an intentional first `bun install` to generate `bun.lock`.
4. Run `mise lock` and commit `mise.lock`.
5. After lockfiles exist, CI uses `mise install --locked` (or equivalent strict mode) and `bun install --frozen-lockfile`.
6. Create workspace package manifests with exact-pinned package-specific dependencies (`zod`, `openai`, etc.).
7. Run `mise run check:all` before the first code commit.

Do not copy package-specific runtime dependencies into the root simply for convenience; keep provider/store/tool dependencies in their owning adapters.
