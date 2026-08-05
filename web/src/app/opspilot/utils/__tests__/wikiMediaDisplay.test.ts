import { describe, expect, it } from "vitest";
import {
  applyWikiMediaDisplayUrls,
  collectBareWikiMediaLocators,
  collectWikiMediaLocators,
  normalizeWikiMediaLocator,
} from "../wikiMediaDisplay";

describe("wikiMediaDisplay", () => {
  const sha = "6".repeat(64);
  const locator = `wiki/media/3/5/${sha}.png`;

  it("collects bare and slash-prefixed locators", () => {
    const md = `![](${locator})\n<img src="/${locator}" />`;
    expect(collectWikiMediaLocators(md).sort()).toEqual([locator]);
    expect(normalizeWikiMediaLocator(`/${locator}`)).toBe(locator);
  });

  it("rewrites bare locators and refreshes stale signed urls", () => {
    const fresh = `https://minio.example/${locator}?sig=fresh`;
    const stale = `http://10.10.41.149:9000/munchkin-private/${locator}?Signature=old`;
    const md = `<img src="${stale}" /><img src="${locator}" />`;
    const out = applyWikiMediaDisplayUrls(md, { [locator]: fresh });
    expect(out).toContain(fresh);
    expect(out).not.toContain("Signature=old");
    expect(out).not.toContain(`src="${locator}"`);
    expect(out).not.toContain("munchkin-private/https://");
  });

  it("keeps markdown image closing paren when refreshing signed url", () => {
    const fresh = `https://minio.example/${locator}?sig=fresh`;
    const stale = `http://10.10.41.149:9000/munchkin-private/${locator}?Signature=old`;
    const md = `![cover](${stale})`;
    const out = applyWikiMediaDisplayUrls(md, { [locator]: fresh });
    expect(out).toBe(`![cover](${fresh})`);
  });

  it("accepts same-origin proxy display urls", () => {
    const proxy = `/api/proxy/opspilot/wiki_mgmt/media/?locator=${encodeURIComponent(locator)}&exp=1&sig=abc`;
    const md = `![cover](${locator})`;
    const out = applyWikiMediaDisplayUrls(md, { [locator]: proxy });
    expect(out).toBe(`![cover](${proxy})`);
  });

  it("does not nest proxy urls when locator appears unencoded in query", () => {
    const stale = `/api/proxy/opspilot/wiki_mgmt/media/?locator=${locator}&exp=1&sig=old`;
    const fresh = `/api/proxy/opspilot/wiki_mgmt/media/?locator=${encodeURIComponent(locator)}&exp=2&sig=new`;
    const md = `![cover](${stale})`;
    expect(collectBareWikiMediaLocators(md)).toEqual([]);
    const out = applyWikiMediaDisplayUrls(md, { [locator]: fresh });
    expect(out).toBe(`![cover](${fresh})`);
    expect(out).not.toContain("locator=/api/proxy");
  });

  it("rewrites every bare locator in one pass", () => {
    const a = `wiki/media/3/5/${"a".repeat(64)}.png`;
    const b = `wiki/media/3/5/${"b".repeat(64)}.png`;
    const md = `![one](${a})\n![two](${b})`;
    const out = applyWikiMediaDisplayUrls(md, {
      [a]: `https://cdn/${a}`,
      [b]: `https://cdn/${b}`,
    });
    expect(out).toContain(`https://cdn/${a}`);
    expect(out).toContain(`https://cdn/${b}`);
    expect(collectBareWikiMediaLocators(out)).toEqual([]);
  });
});
