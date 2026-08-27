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
    },
  },
});
