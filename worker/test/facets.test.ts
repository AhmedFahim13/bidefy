import { describe, expect, it } from "vitest";
import { CONSTRUCTION_TYPES, facetQuery } from "../src/query";

const base = { q: "", status: "Live", ministry: "", district: "", category: "", page: 1, size: 25 };

describe("facetQuery", () => {
  it("narrows the category counts to the chosen ministry", () => {
    const { sql, params } = facetQuery({ ...base, ministry: "Ministry of Defence" }, "category");
    expect(sql).toContain("SELECT category AS v");
    expect(sql).toContain("ministry = ?");
    expect(params).toContain("Ministry of Defence");
    expect(params).toContain("Live");          // the list's own status filter still applies
  });

  it("never constrains a facet by itself, so the ministry list stays complete", () => {
    const { sql, params } = facetQuery({ ...base, ministry: "Ministry of Defence" }, "ministry");
    expect(sql).not.toContain("ministry = ?");
    expect(params).not.toContain("Ministry of Defence");
  });

  it("the status facet ignores status but keeps the other filters", () => {
    const { sql } = facetQuery({ ...base, status: "Cancelled", ministry: "M" }, "status");
    expect(sql).not.toContain("status = ?");
    expect(sql).toContain("ministry = ?");
  });

  it("counts a construction filter as all of its types", () => {
    const { sql, params } = facetQuery({ ...base, category: "construction" }, "ministry");
    expect(sql).toContain("category IN (?, ?, ?, ?)");
    for (const type of CONSTRUCTION_TYPES) expect(params).toContain(type);
  });

  it("a keyword narrows every facet", () => {
    expect(facetQuery({ ...base, q: "road" }, "category").params).toContain("%road%");
  });

  it("status=all drops the status filter from the other facets", () => {
    expect(facetQuery({ ...base, status: "all" }, "category").sql).not.toContain("status = ?");
  });
});
