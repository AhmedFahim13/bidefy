import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// The include pattern used to be lib/** alone, so a test under app/ was never collected and the API
// proxy -- the path every browser call to the data service takes -- had no tests at all. The alias
// mirrors tsconfig's paths so route files can be imported the way they import each other.
export default defineConfig({
  test: { include: ["{lib,app}/**/*.test.ts"], environment: "node" },
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
});
