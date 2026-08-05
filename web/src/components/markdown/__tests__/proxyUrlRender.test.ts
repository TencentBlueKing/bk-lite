import { describe, expect, it } from "vitest";
import { remark } from "remark";
import html from "remark-html";
import gfm from "remark-gfm";
import {
  extractMarkdownImages,
  restoreMarkdownImages,
  repairBareWikiMediaImgSrcs,
} from "../wikiMarkdownImages";

const FOCUS =
  "68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5";
const LOCATOR = `wiki/media/3/5/${FOCUS}.png`;
const PROXY =
  `/api/proxy/opspilot/wiki_mgmt/media/?locator=wiki%2Fmedia%2F3%2F5%2F${FOCUS}.png&exp=1786009357&sig=1e4f671a97f9157f434eb472efa4835a8dd62a15b197731a9d31e67a955212f0`;

const SAMPLE = `# 蓝鲸平台简介

蓝鲸平台是面向社区用户和企业用户的基于Paas的运维技术解决方案套件
版本包含社区版、企业版分别面向社区用户和企业用户

支持公有云环境、私有环境的独立搭建部署

![A 3D rendering of a thick, green hardcover book or software box set, presented at a slight angle. The cover is a gradient of deep forest green at the bottom to a brighter leaf green at the top. In the center of the front cover, there is a white stylized logo resembling an apple or a cloud, with the Chinese text "蓝鲸智云" (Blue Whale Intelligent Cloud) underneath it, followed by the title "《社区版》" (Community Edition) in white characters. The top right corner features a subtle, white network graphic consisting of interconnected dots and lines, suggesting connectivity or data. The bottom left corner of the front cover is decorated with sharp, colorful geometric streaks in shades of purple, blue, teal, and yellow. The bottom right corner prominently displays the "Tencent 腾讯" logo in white. The spine of the book contains vertical Chinese text and a barcode at the bottom, along with several small circular certification icons. The entire object is set against a plain white background with a soft reflection beneath it.](${PROXY})

永久免费开放
`;

describe("full sample proxy render", () => {
  it("never emits bare locator as img src", async () => {
    const { markdown, images } = extractMarkdownImages(SAMPLE);
    expect(images[0]?.src).toBe(PROXY);
    let out = String(await remark().use(gfm).use(html).process(markdown));
    out = restoreMarkdownImages(out, images);
    out = repairBareWikiMediaImgSrcs(out, SAMPLE);
    const img = out.match(/<img[^>]+>/)?.[0] || "";
    expect(img).toContain("/api/proxy/opspilot/wiki_mgmt/media/");
    expect(img).not.toMatch(/src="wiki\/media\//);
    expect(img).toContain(FOCUS);
  });

  it("repairs bare src using source markdown proxy url", () => {
    const broken = `<p><img src="${LOCATOR}" alt="x" /></p>`;
    const fixed = repairBareWikiMediaImgSrcs(broken, SAMPLE);
    expect(fixed).toContain(`src="${PROXY.replace(/&/g, "&amp;")}"`);
    expect(fixed).not.toMatch(/src="wiki\/media\//);
  });
});
