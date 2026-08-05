import { describe, expect, it } from "vitest";
import {
  applyWikiMediaDisplayUrls,
  collectBareWikiMediaLocators,
  collectWikiMediaLocators,
  isWikiMediaDisplayUrl,
} from "../wikiMediaDisplay";

describe("wiki media display prefer proxy", () => {
  const locator =
    "wiki/media/3/5/68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5.png";
  const minio =
    `http://10.10.41.149:9000/munchkin-private/${locator}` +
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc";
  const proxy =
    `/api/proxy/opspilot/wiki_mgmt/media/?locator=${encodeURIComponent(locator)}&exp=1&sig=abc`;

  it("collects locator inside minio signed markdown image", () => {
    expect(collectWikiMediaLocators(`![x](${minio})`)).toEqual([locator]);
    expect(collectBareWikiMediaLocators(`![x](${minio})`)).toEqual([]);
  });

  it("upgrades minio signed url to same-origin proxy without nesting", () => {
    const out = applyWikiMediaDisplayUrls(`![x](${minio})`, {
      [locator]: proxy,
    });
    expect(out).toBe(`![x](${proxy})`);
    expect(isWikiMediaDisplayUrl(proxy)).toBe(true);
    expect(collectBareWikiMediaLocators(out)).toEqual([]);
  });

  it("does not treat unencoded locator= query as bare", () => {
    const stale = `/api/proxy/opspilot/wiki_mgmt/media/?locator=${locator}&exp=1&sig=old`;
    expect(collectBareWikiMediaLocators(`![x](${stale})`)).toEqual([]);
    const out = applyWikiMediaDisplayUrls(`![x](${stale})`, {
      [locator]: proxy,
    });
    expect(out).toBe(`![x](${proxy})`);
    expect(out).not.toContain("locator=/api/proxy");
  });
});
