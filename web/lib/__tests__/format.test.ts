import { describe, expect, it } from "vitest";
import { buildQuery, daysLeft, formatCrore, formatDate, isStale } from "../format";

describe("format", () => {
  it("formatDate renders ISO minutes as a short date", () => {
    expect(formatDate("2026-09-13T11:00")).toBe("13 Sep 2026, 11:00");
    expect(formatDate("2026-09-13")).toBe("13 Sep 2026");
    expect(formatDate(null)).toBe("");
  });
  it("formatCrore shows taka in crore or lakh", () => {
    expect(formatCrore(2.433)).toBe("2.43 crore");
    expect(formatCrore(0.079)).toBe("7.9 lakh");
    expect(formatCrore(null)).toBe("");
  });
  it("isStale is true past 36 hours", () => {
    const now = new Date("2026-09-14T00:00:00Z");
    expect(isStale("20260913T070000000000Z", now)).toBe(false);
    expect(isStale("20260912T070000000000Z", now)).toBe(true);
    expect(isStale(null, now)).toBe(true);
  });
  it("daysLeft counts whole days until closing", () => {
    expect(daysLeft("2026-09-28T13:00", new Date("2026-09-13T12:00:00Z"))).toBe(14);
    expect(daysLeft(null, new Date())).toBeNull();
  });
  it("buildQuery drops empties and defaults", () => {
    expect(buildQuery({ q: "printer", status: "Live", ministry: "", page: 1 })).toBe("q=printer");
    expect(buildQuery({ q: "", status: "all", page: 3 })).toBe("status=all&page=3");
  });
});
