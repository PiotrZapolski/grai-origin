import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Frontend test configuration. jsdom is required by the component tests
// from tasks E1-E10, which subsequent tasks write.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
  },
});
