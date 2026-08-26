import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { Timeline } from "../components/timeline/Timeline";

// vitest.config.ts has `globals: false`, so @testing-library/react does not
// register its own cleanup and the next tests in the file would render on the
// leftovers of the previous ones. Without this the "previous screen" counts as
// the current one.
afterEach(cleanup);

describe("E7 chronology", () => {
  it("highlights the earliest entry", () => {
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" },
      { id: "b", name: "B", published: "1998-06-01", published_source: "manual" }]} />);
    expect(screen.getByTestId("earliest").textContent).toContain("A");
  });

  it("skips candidates with no date", () => {
    // D10: for an entry outside the manifest the axis shows nothing
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" },
      { id: "b", name: "B", published: null, published_source: null }]} />);
    expect(screen.queryByText("B")).toBeNull();
  });

  it("says where the date comes from", () => {
    render(<Timeline items={[
      { id: "a", name: "A", published: "1975-02-24", published_source: "manual" }]} />);
    expect(screen.getByText(/release metadata, not from the video service/i)).toBeInTheDocument();
  });

  it("does not render the axis when no candidate has a date", () => {
    const { container } = render(<Timeline items={[
      { id: "b", name: "B", published: null, published_source: null }]} />);
    expect(container.querySelector("[data-testid='axis']")).toBeNull();
  });
});
