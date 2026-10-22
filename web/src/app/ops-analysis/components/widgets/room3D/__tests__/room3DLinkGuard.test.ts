import { describe, expect, it } from "vitest";

import { canOpenRoom3DRackLink } from "../room3DData";

describe("canOpenRoom3DRackLink", () => {
  it("blocks conflict placeholder racks and allows normal racks", () => {
    expect(canOpenRoom3DRackLink({ is_conflict: true })).toBe(false);
    expect(canOpenRoom3DRackLink({ is_conflict: false })).toBe(true);
    expect(canOpenRoom3DRackLink({})).toBe(true);
  });
});
