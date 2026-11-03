import { describe, expect, it } from "vitest";
import { alertErrorText, matchFilters, notificationFor } from "../src/alerts";

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

describe("alertErrorText", () => {
  it("keeps the error's kind and message, short, with long numbers masked", () => {
    const e = new Error("D1_ERROR: no such column: fetched_at for tender 1365277 " + "x".repeat(400));
    const text = alertErrorText(e);
    expect(text.startsWith("Error: D1_ERROR: no such column: fetched_at for tender #")).toBe(true);
    expect(text).not.toContain("1365277");
    expect(text.length).toBeLessThanOrEqual(200);
  });

  it("describes something thrown that is not an Error", () => {
    expect(alertErrorText("boom")).toBe("boom");
    expect(alertErrorText(undefined)).toBe("unknown");
  });
});
