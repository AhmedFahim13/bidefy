import { describe, expect, it } from "vitest";
import { hashIp, validateAccessRequest } from "../src/access";

const good = { name: "Rahim Uddin", organisation: "Rahim Construction", role: "Owner", bids_on: "LGED rural roads in Rangpur", value_band: "1_to_10_crore", contact: "01700000000", note: "" };

describe("validateAccessRequest", () => {
  it("accepts a complete request and trims", () => {
    const r = validateAccessRequest({ ...good, name: "  Rahim Uddin  " });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.name).toBe("Rahim Uddin");
  });
  it("rejects the honeypot, missing fields and bad bands", () => {
    expect(validateAccessRequest({ ...good, website: "http://spam" }).ok).toBe(false);
    expect(validateAccessRequest({ ...good, name: "R" }).ok).toBe(false);
    expect(validateAccessRequest({ ...good, value_band: "huge" }).ok).toBe(false);
    expect(validateAccessRequest({ ...good, bids_on: "" }).ok).toBe(false);
  });
  it("truncates long notes", () => {
    const r = validateAccessRequest({ ...good, note: "x".repeat(900) });
    expect(r.ok && r.value.note.length).toBe(500);
  });
});

describe("hashIp", () => {
  it("is stable and does not reveal the ip", async () => {
    const a = await hashIp("203.0.113.5");
    expect(a).toBe(await hashIp("203.0.113.5"));
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(a).not.toContain("203");
  });
});
