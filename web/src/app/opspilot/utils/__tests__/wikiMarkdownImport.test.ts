import { describe, expect, it } from "vitest";
import {
  formatMarkdownImportGovernanceError,
  initialCreateDirectoriesFromFolders,
  markdownImportAccept,
  markdownImportFilePattern,
  markdownImportGovernanceErrorView,
  okfSkippedReasonLabel,
} from "../wikiMarkdownImport";

describe("wikiMarkdownImport", () => {
  it("uses zip-only accept and default folders for OKF", () => {
    expect(markdownImportAccept("okf")).toBe(".zip");
    expect(markdownImportFilePattern("okf").test("bundle.zip")).toBe(true);
    expect(markdownImportFilePattern("okf").test("page.md")).toBe(false);
    expect(initialCreateDirectoriesFromFolders("okf")).toBe(true);
  });

  it("keeps markdown accept and defaults folders off", () => {
    expect(markdownImportAccept("markdown")).toBe(".md,.markdown,.zip");
    expect(markdownImportFilePattern("markdown").test("page.md")).toBe(true);
    expect(initialCreateDirectoriesFromFolders("markdown")).toBe(false);
  });

  it("explains reserved OKF skips in plain language", () => {
    const t = (id: string) =>
      ({
        "wiki.okfSkipReasonReserved": "目录或更新日志，按规范不作为知识页导入",
        "wiki.okfSkipReasonTypeMissing": "缺少非空 type，无法作为知识页",
        "wiki.okfSkipReasonUnknown": "已跳过（{reason}）",
      })[id] || id;
    expect(okfSkippedReasonLabel(t, "reserved")).toContain("目录或更新日志");
    expect(okfSkippedReasonLabel(t, "type_missing")).toContain("type");
    expect(okfSkippedReasonLabel(t, "weird")).toBe("已跳过（weird）");
  });
});

describe("markdownImportGovernanceErrorView", () => {
  const t = (id: string) =>
    ({
      "wiki.okfNoConcepts": "没有可导入的知识页",
      "wiki.okfNoConceptsNeedFrontmatter": "请补 YAML 与 type。",
      "wiki.okfNoConceptsTypeMissing": "请补非空 type。",
      "wiki.markdownImportPreflightFailed": "预检失败。",
    })[id] || id;

  it("keeps the toast title short and puts the fix in description", () => {
    const view = markdownImportGovernanceErrorView(t, {
      code: "okf_no_concepts",
      details: { skipped: [{ path: "wiki/a.md", reason: "yaml_invalid" }] },
    });
    expect(view.title).toBe("没有可导入的知识页");
    expect(view.description).toBe("请补 YAML 与 type。");
    expect(view.example).toContain("type: concept");
    expect(formatMarkdownImportGovernanceError(t, { code: "okf_no_concepts" })).toBe(
      "没有可导入的知识页",
    );
  });

  it("names the ZIP size limit and actual size", () => {
    const t = (id: string) =>
      ({
        "wiki.archiveTooLarge": "ZIP 超过大小限制",
        "wiki.archiveTooLargeDesc": "当前文件 {actual}，压缩包上限 {max}。",
      })[id] || id;
    const view = markdownImportGovernanceErrorView(t, {
      code: "archive_size_exceeded",
      details: { max_bytes: 50 * 1024 * 1024, actual_bytes: 80 * 1024 * 1024 },
    });
    expect(view.title).toBe("ZIP 超过大小限制");
    expect(view.description).toBe("当前文件 80 MB，压缩包上限 50 MB。");
  });

  it("groups missing OKF images by markdown path", () => {
    const t = (id: string) =>
      ({
        "wiki.okfImagesMissing": "缺图",
        "wiki.okfImagesMissingDesc": "补图：",
        "wiki.okfImageMissingNotFound": "没有该文件",
        "wiki.okfImageMissingTruncated": "还有 {count} 条",
      })[id] || id;
    const view = markdownImportGovernanceErrorView(t, {
      code: "okf_images_missing",
      details: {
        missing: [
          { archive_path: "guides/a.md", image_path: "assets/x.png", reason: "not_found" },
          { archive_path: "guides/a.md", image_path: "assets/y.png", reason: "not_found" },
        ],
        truncated: true,
        total: 3,
      },
    });
    expect(view.title).toBe("缺图");
    expect(view.description).toContain("guides/a.md");
    expect(view.description).toContain("assets/x.png");
    expect(view.description).toContain("还有 1 条");
  });

  it("tells users to add type when YAML exists", () => {
    expect(
      markdownImportGovernanceErrorView(t, {
        code: "okf_no_concepts",
        details: { skipped: [{ path: "wiki/a.md", reason: "type_missing" }] },
      }).description,
    ).toBe("请补非空 type。");
  });
});
