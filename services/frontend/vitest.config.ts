import { defineConfig } from "vitest/config";

// jsdom so the API client can use localStorage/fetch; tests import { describe,
// it, expect, vi } from "vitest" explicitly (no reliance on global types).
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
