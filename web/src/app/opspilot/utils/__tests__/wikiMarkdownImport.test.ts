import { describe, expect, it } from "vitest";
import en from "../../locales/en.json";
import zh from "../../locales/zh.json";
import {
  formatMarkdownImportGovernanceError,
  initialCreateDirectoriesFromFolders,
  isBackgroundMarkdownImport,
  OKF_IMPORT_HOLD_TIMEOUT_MS,
  markdownImportAccept,
  markdownImportFilePattern,
  markdownImportGovernanceErrorView,
  okfSkippedReasonLabel,
  resolveOkfImportProgress,
  unwrapMarkdownImportExecuteResult,
  type ResolveOkfImportProgressInput,
} from "../wikiMarkdownImport";

describe("wikiMarkdownImport", () => {
  it("uses zip-only accept and default folders for OKF", () => {
    expect(markdownImportAccept()).toBe(".zip");
    expect(markdownImportFilePattern().test("bundle.zip")).toBe(true);
    expect(markdownImportFilePattern().test("page.md")).toBe(false);
    expect(initialCreateDirectoriesFromFolders()).toBe(false);
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

describe("unwrapMarkdownImportExecuteResult", () => {
  it("peels nested result/data envelopes from the execute payload", () => {
    expect(
      unwrapMarkdownImportExecuteResult({
        result: true,
        data: {
          async: true,
          accepted: true,
          queued: true,
          status: "running",
          stage: "queued",
          build_record_id: 12,
        },
      }),
    ).toEqual({
      async: true,
      accepted: true,
      queued: true,
      status: "running",
      stage: "queued",
      build_record_id: 12,
    });
  });

  it("treats queued execute payloads as background import", () => {
    expect(
      isBackgroundMarkdownImport(
        unwrapMarkdownImportExecuteResult({
          result: true,
          data: { accepted: true, build_record_id: 8, status: "running" },
        }),
      ),
    ).toBe(true);
    expect(
      isBackgroundMarkdownImport({
        generation_id: 3,
        counts: { created: 2, updated: 1, candidate: 0 },
      }),
    ).toBe(false);
  });
});

const NOW = Date.parse("2026-10-22T04:00:00Z");

const progressInput = (
  overrides: Partial<ResolveOkfImportProgressInput> = {},
): ResolveOkfImportProgressInput => ({
  items: [],
  trackedBuildRecordId: 12,
  acceptedStatus: "running",
  holding: true,
  holdStartedAt: NOW - 5_000,
  seenActive: false,
  now: NOW,
  ...overrides,
});

describe("resolveOkfImportProgress", () => {
  it("keeps zh and en progress copy usable", () => {
    expect(zh.wiki.okfImportProgress).toContain("{progress}");
    expect(en.wiki.okfImportProgress).toContain("{progress}");
    expect(zh.wiki.okfImportEnriching.length).toBeGreaterThan(0);
    expect(en.wiki.okfImportEnriching.length).toBeGreaterThan(0);
    expect(zh.wiki.okfImportFailed.length).toBeGreaterThan(0);
    expect(en.wiki.okfImportFailed.length).toBeGreaterThan(0);
  });

  it("reports writing progress while the tracked record is running", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          items: [{ id: 12, status: "running", progress: 40, updated_at: new Date(NOW).toISOString() }],
        }),
      ),
    ).toEqual({ phase: "writing", progress: 40 });
  });

  it("reports enriching after success while search enrichment is running", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          seenActive: true,
          holding: false,
          items: [{
            id: 12,
            status: "success",
            progress: 100,
            updated_at: new Date(NOW).toISOString(),
            maintenance: { search_enrichment: "running" },
          }],
        }),
      ),
    ).toEqual({ phase: "enriching" });
  });

  it("completes when success and search enrichment are done", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          seenActive: true,
          holding: false,
          items: [{
            id: 12,
            status: "success",
            progress: 100,
            updated_at: new Date(NOW).toISOString(),
            maintenance: { search_enrichment: "done" },
          }],
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "success" });
  });

  it("clears a failed import instead of holding the buttons", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          items: [{ id: 12, status: "failed", progress: 0, updated_at: new Date(NOW).toISOString() }],
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "failed" });
    expect(
      resolveOkfImportProgress(
        progressInput({
          items: [{ id: 12, status: "partial", updated_at: new Date(NOW).toISOString() }],
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "failed" });
    expect(
      resolveOkfImportProgress(
        progressInput({
          items: [],
          acceptedStatus: "cancelled",
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "failed" });
  });

  it("releases a fast success that never showed running", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          seenActive: false,
          holding: true,
          items: [{
            id: 12,
            status: "success",
            progress: 100,
            updated_at: new Date(NOW).toISOString(),
            maintenance: { search_enrichment: "done" },
          }],
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "success" });
  });

  it("holds at the start and times out when the record never appears", () => {
    expect(resolveOkfImportProgress(progressInput({ items: [] }))).toEqual({
      phase: "holding",
    });
    expect(
      resolveOkfImportProgress(
        progressInput({
          items: [],
          acceptedStatus: "running",
          holdStartedAt: NOW - OKF_IMPORT_HOLD_TIMEOUT_MS - 1,
        }),
      ),
    ).toEqual({ phase: "completed", outcome: "failed" });
  });

  it("does not treat an older finished import as the one just accepted", () => {
    expect(
      resolveOkfImportProgress(
        progressInput({
          trackedBuildRecordId: null,
          acceptedStatus: null,
          items: [{
            id: 3,
            status: "success",
            updated_at: new Date(NOW - 60 * 60 * 1000).toISOString(),
            maintenance: { search_enrichment: "done" },
          }],
        }),
      ),
    ).toEqual({ phase: "holding" });
  });
});
