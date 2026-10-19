import { describe, expect, it } from "vitest";

import { canOpenRoom3DRackLink } from "../room3DData";
import { shouldShowRoom3DDeviceLinkHint } from "../room3DLinkHint";

describe("canOpenRoom3DRackLink", () => {
  it("blocks conflict placeholder racks and allows normal racks", () => {
    expect(canOpenRoom3DRackLink({ is_conflict: true })).toBe(false);
    expect(canOpenRoom3DRackLink({ is_conflict: false })).toBe(true);
    expect(canOpenRoom3DRackLink({})).toBe(true);
  });
});

describe("shouldShowRoom3DDeviceLinkHint", () => {
  const device = { device_id: "dev-1" };
  const rack = { is_conflict: false };
  const link = { kind: "data" as const };

  it("shows only for a real device on a linkable rack in view mode", () => {
    expect(shouldShowRoom3DDeviceLinkHint("view", link, rack, device)).toBe(true);
    expect(shouldShowRoom3DDeviceLinkHint("edit", link, rack, device)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("share", link, rack, device)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("view", { kind: "title" }, rack, device)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("view", { kind: "none" }, rack, device)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("view", undefined, rack, device)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("view", link, rack, null)).toBe(false);
    expect(shouldShowRoom3DDeviceLinkHint("view", link, null, device)).toBe(false);
    expect(
      shouldShowRoom3DDeviceLinkHint("view", link, { is_conflict: true }, device),
    ).toBe(false);
  });
});
