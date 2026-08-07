import { describe, expect, it } from "vitest";
import {
  isRedundantWikiAiSummary,
  pickWikiMaterialBodyMarkdown,
} from "../wikiMaterialDisplay";

describe("wikiMaterialDisplay", () => {
  it("picks parsed markdown over ai summary", () => {
    expect(pickWikiMaterialBodyMarkdown("# full", "short")).toBe("# full");
    expect(pickWikiMaterialBodyMarkdown("", "short")).toBe("short");
  });

  it("treats image-bearing ai summary as redundant when parsed exists", () => {
    const parsed = "# title\n\n![alt](/api/proxy/opspilot/wiki_mgmt/media/?locator=x)\n";
    const summary = "![A 3D digital rendering of a software product box](wiki/media/3/5/abc.png)";
    expect(isRedundantWikiAiSummary(parsed, summary)).toBe(true);
  });

  it("treats truncated image alt in ai summary as redundant", () => {
    const parsed =
      "# 蓝鲸平台简介\n\n![green](/api/proxy/...)\n\n![blue full alt](/api/proxy/...)\n";
    const summary =
      "![A 3D digital rendering of a software product box set against a white background. The box is predominantly a deep royal blue with a subtle gradient that darkens toward the bottom. On the front";
    expect(isRedundantWikiAiSummary(parsed, summary)).toBe(true);
  });

  it("keeps short text summary when distinct", () => {
    expect(
      isRedundantWikiAiSummary(
        "# long body with many slides...",
        "蓝鲸平台社区版与企业版简介。",
      ),
    ).toBe(false);
  });
});
