import { describe, expect, it } from "vitest";
import { getDefaultConfig } from "../chatflow";

describe("getDefaultConfig intent classification", () => {
  it("seeds the first intent from the page language", () => {
    const config = getDefaultConfig("intent_classification", {
      defaultIntent: "Default intent",
    }) as { intents: Array<{ name: string }> };
    expect(config.intents).toEqual([{ name: "Default intent" }]);
  });

  it("keeps the Chinese stock name when no locale is passed", () => {
    const config = getDefaultConfig("intent_classification") as {
      intents: Array<{ name: string }>;
    };
    expect(config.intents).toEqual([{ name: "默认意图" }]);
  });
});
