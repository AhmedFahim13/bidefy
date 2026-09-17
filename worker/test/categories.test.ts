import { describe, expect, it } from "vitest";
import { matchFilters } from "../src/alerts";
import { CONSTRUCTION_TYPES, categoryMatches, tenderListQuery } from "../src/query";

const base = { q: "", status: "Live", ministry: "", district: "", page: 1, size: 25 };

describe("construction and its types", () => {
  it("construction matches every construction tender, a type matches only itself", () => {
    for (const have of CONSTRUCTION_TYPES) expect(categoryMatches(have, "construction")).toBe(true);
    expect(categoryMatches("medical", "construction")).toBe(false);
    expect(categoryMatches("roads_bridges", "roads_bridges")).toBe(true);
    expect(categoryMatches("construction", "roads_bridges")).toBe(false);   // an unstated type is not a road
    expect(categoryMatches(null, "medical")).toBe(false);
  });

  it("the tender list query expands construction into its types", () => {
    const { sql, params } = tenderListQuery({ ...base, category: "construction" });
    expect(sql).toContain("category IN (?, ?, ?, ?)");
    expect(params.slice(1, 5)).toEqual(CONSTRUCTION_TYPES);
    const one = tenderListQuery({ ...base, category: "medical" });
    expect(one.sql).toContain("category = ?");
    expect(one.params).toContain("medical");
  });

  it("an alert for construction fires on a road tender, an alert for roads does not fire on plain construction", () => {
    const road = { tender_id: "1", title: "Carpeting of road", ministry: "M", status: "Live", category: "roads_bridges", procuring_entity: "PE", closing_at: null };
    const plain = { ...road, tender_id: "2", category: "construction" };
    expect(matchFilters(road, [{ category: "construction" }])).toBe(true);
    expect(matchFilters(plain, [{ category: "construction" }])).toBe(true);
    expect(matchFilters(plain, [{ category: "roads_bridges" }])).toBe(false);
  });
});
