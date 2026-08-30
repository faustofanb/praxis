import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.{test,spec}.ts"],
    // *.bun.test.ts files exercise bun:sqlite and run under `bun test`
    // (mise run test:store); Node-collecting them would crash on import.
    exclude: ["**/node_modules/**", "**/dist/**", "**/fixtures/**", "**/*.bun.test.ts"],
    restoreMocks: true,
    clearMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "html"],
      exclude: ["**/dist/**", "**/fixtures/**", "**/*.d.ts"],
      thresholds: {
        // Core coverage target (M7-T010): measured baseline at the decision
        // commit was 97.58% statements (847/868) and 94.31% branches
        // (497/527); the floor sits below it so natural variance from
        // active development stays legal while real erosion fails CI
        // (check:all -> test:coverage). Scoped to packages/core per the
        // docs/03 M7 row; other packages have no threshold yet.
        "packages/core/src/**": {
          statements: 95,
          branches: 90,
        },
      },
    },
  },
});
