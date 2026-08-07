import { describe, expect, it } from "vitest";
import {
  extractMarkdownImages,
  restoreMarkdownImages,
} from "../wikiMarkdownImages";

describe("wikiMarkdownImages", () => {
  it("preserves minio signed url through remark placeholder roundtrip", () => {
    const locator =
      "wiki/media/3/5/68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5.png";
    const src = `http://10.10.41.149:9000/munchkin-private/${locator}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=minio%2F20260730%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Signature=abc`;
    const alt =
      "A 3D rendering of a thick, green hardcover book or software box set";
    const md = `# Title\n\n![${alt}](${src})\n\ntext`;
    const { markdown, images } = extractMarkdownImages(md);
    expect(images).toHaveLength(1);
    expect(images[0].src).toBe(src);
    expect(markdown).toContain("@@WIKI_MD_IMG_0@@");
    expect(markdown).not.toContain(locator);

    const restored = restoreMarkdownImages(
      `<p>@@WIKI_MD_IMG_0@@</p><p>text</p>`,
      images,
    );
    expect(restored).toContain(`src="${src.replace(/&/g, "&amp;")}"`);
    expect(restored).toContain("<img ");
    expect(restored).not.toContain("@@WIKI_MD_IMG_0@@");
  });

  it("still extracts bare wiki/media so renderer can show img tag", () => {
    const locator =
      "wiki/media/3/5/68d90276d0e8e1b3009cbf1b1310bc70f7616f4367ac67b45b5e9ca676ef48e5.png";
    const { images } = extractMarkdownImages(`![cover](${locator})`);
    expect(images[0].src).toBe(locator);
  });
});
