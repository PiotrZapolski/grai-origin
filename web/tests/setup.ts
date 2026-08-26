// DOM matchers for the component tests (toBeInTheDocument, toHaveClass, ...).
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// `vitest.config.ts` has `globals: false`, so @testing-library/react does not
// register its own cleanup by itself. Without this the next test in the same
// file renders on the leftovers of the previous DOM, and `screen.getByText`
// finds an element from the old render, so the assertion passes for the wrong
// reason.
afterEach(() => {
  cleanup();
});
