import { describe, expect, it } from "vitest";
import { matchFilters, notificationFor } from "../src/alerts";

const t = {
  tender_id: "1",
  title: "Purchase of Dot Matrix Printer Ribbon",
  ministry: "Ministry of Energy",
  status: "Live",
  category: "it_equipment",
  procuring_entity: "Kushtia PBS",
  closing_at: "2026-09-28T13:00",
};

describe("matchFilters", () => {
  it("matches keyword case-insensitively, ministry and category exactly", () => {
    expect(matchFilters(t, [{ q: "printer" }])).toBe(true);
    expect(matchFilters(t, [{ q: "PRINTER", ministry: "Ministry of Energy" }])).toBe(true);
    expect(matchFilters(t, [{ q: "printer", ministry: "Ministry of Finance" }])).toBe(false);
    expect(matchFilters(t, [{ category: "it_equipment" }])).toBe(true);
    expect(matchFilters(t, [{ category: "medical" }, { q: "ribbon" }])).toBe(true);
    expect(matchFilters(t, [{ status: "Cancelled" }])).toBe(false);
  });
  it("an empty filter row never matches everything", () => {
    expect(matchFilters(t, [{}])).toBe(false);
    expect(matchFilters(t, [])).toBe(false);
  });
});

describe("notificationFor", () => {
  it("builds a compact payload with the tender url", () => {
    const n = notificationFor(t, "https://bidefy.vercel.app");
    expect(n.title.length).toBeLessThanOrEqual(80);
    expect(n.body).toContain("Kushtia PBS");
    expect(n.url).toBe("https://bidefy.vercel.app/t/1");
    expect(n.tag).toBe("tender-1");
  });
});
