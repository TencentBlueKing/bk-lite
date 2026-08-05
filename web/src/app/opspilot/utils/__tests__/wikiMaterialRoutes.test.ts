import { describe, expect, it } from "vitest";
import {
  buildWikiDetailTabPath,
  buildWikiMaterialDetailPath,
  buildWikiMaterialListPath,
} from "../wikiMaterialRoutes";

describe("wikiMaterialRoutes", () => {
  it("builds detail path with materialId and preserves other query", () => {
    expect(
      buildWikiMaterialDetailPath({
        kbId: 3,
        materialId: 5,
        searchParams: "id=3&tab=overview&name=demo",
      }),
    ).toBe(
      "/opspilot/wiki/detail?id=3&tab=material&name=demo&materialId=5",
    );
  });

  it("builds list path by clearing materialId", () => {
    expect(
      buildWikiMaterialListPath({
        kbId: 3,
        searchParams: "id=3&tab=material&materialId=5&name=demo",
      }),
    ).toBe("/opspilot/wiki/detail?id=3&tab=material&name=demo");
  });

  it("clears materialId when switching left-menu tabs", () => {
    expect(
      buildWikiDetailTabPath({
        kbId: 11,
        tab: "knowledge",
        searchParams:
          "id=11&name=22&tab=material&materialId=16&wiki_page=83",
      }),
    ).toBe(
      "/opspilot/wiki/detail?id=11&name=22&tab=knowledge&wiki_page=83",
    );
  });

  it("opens material list from left menu even when currently on material detail", () => {
    expect(
      buildWikiDetailTabPath({
        kbId: 11,
        tab: "material",
        searchParams: "id=11&name=22&tab=material&materialId=16&wiki_page=83",
      }),
    ).toBe("/opspilot/wiki/detail?id=11&name=22&tab=material");
  });

  it("keeps knowledge selection when rebuilding knowledge menu link", () => {
    expect(
      buildWikiDetailTabPath({
        kbId: 11,
        tab: "knowledge",
        searchParams: "id=11&name=22&tab=knowledge&wiki_page=83&wiki_view=page",
      }),
    ).toBe(
      "/opspilot/wiki/detail?id=11&name=22&tab=knowledge&wiki_page=83&wiki_view=page",
    );
  });
});
