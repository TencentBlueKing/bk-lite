import { describe, expect, it } from "vitest";
import {
  extractMarkdownImages,
  repairBareWikiMediaImgSrcs,
  restoreMarkdownImages,
} from "../wikiMarkdownImages";
import { remark } from "remark";
import html from "remark-html";
import gfm from "remark-gfm";

describe("URL-anchored image extract", () => {
  const p1 =
    "/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki%2Fmedia%2F3%2F5%2F68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5.png&exp=1&sig=a";
  const p2 =
    "/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki%2Fmedia%2F3%2F5%2Fee5f52a3cfece2420320781c5ec0fbb405a0099a3aaf0c6a08d0e38b10b861e9.png&exp=1&sig=b";
  const p3 =
    "/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki%2Fmedia%2F3%2F5%2Ff4a433c224846f311c739085b1167934e857a2a0a1a21f2f9d3c9cf3189303b9.jpg&exp=1&sig=c";

  it("extracts all images when a middle alt contains ]", async () => {
    const md = [
      `![first (ok)](${p1})`,
      `![second has ] bracket inside alt text here](${p2})`,
      `![third](${p3})`,
    ].join("\n\n");
    const { images, markdown } = extractMarkdownImages(md);
    expect(images.map((i) => i.src)).toEqual([p1, p2, p3]);
    expect(images[1].alt).toContain("] bracket");
    expect(markdown).not.toContain("/api/proxy/");
    let out = String(await remark().use(gfm).use(html).process(markdown));
    out = restoreMarkdownImages(out, images);
    out = repairBareWikiMediaImgSrcs(out, md);
    expect(out.match(/<img\b/g)?.length).toBe(3);
    expect(out).not.toMatch(/src="wiki\/media\//);
    expect(out).toContain(p1.replace(/&/g, "&amp;"));
    expect(out).toContain(p2.replace(/&/g, "&amp;"));
  });

  it("repairs bare src from source proxy urls", () => {
    const md = `![x](${p1})`;
    const broken = `<p><img src="wiki/media/3/5/68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5.png" alt="x" /></p>`;
    const fixed = repairBareWikiMediaImgSrcs(broken, md);
    expect(fixed).toContain(p1.replace(/&/g, "&amp;"));
  });
});
