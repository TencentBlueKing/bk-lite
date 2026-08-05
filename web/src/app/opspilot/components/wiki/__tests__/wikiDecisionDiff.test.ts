import { describe, expect, it } from "vitest";
import {
  buildConflictListSubtitle,
  buildKnowledgeConflictDiff,
  formatDiffHighlightLabel,
} from "@/app/opspilot/components/wiki/wikiDecisionDiff";

const labels = {
  added: "新增：",
  removed: "移除：",
  changed: "「{left}」→「{right}」",
};

describe("wikiDecisionDiff", () => {
  it("returns no highlights when bodies are identical", () => {
    const body = "蓝鲸管控平台是基础管控系统。\n\n采用 Server-Proxy-Agent 架构。";
    const diff = buildKnowledgeConflictDiff(body, body);
    expect(diff.highlights).toEqual([]);
    expect(diff.leftSegments.every((segment) => segment.status === "equal")).toBe(
      true,
    );
    expect(diff.rightSegments.every((segment) => segment.status === "equal")).toBe(
      true,
    );
  });

  it("marks a changed sentence on both sides", () => {
    const left = "磁盘使用率达到 80% 时告警。";
    const right = "磁盘使用率达到 85% 时告警。";
    const diff = buildKnowledgeConflictDiff(left, right);
    expect(diff.leftSegments.some((segment) => segment.status === "changed")).toBe(
      true,
    );
    expect(diff.rightSegments.some((segment) => segment.status === "changed")).toBe(
      true,
    );
    expect(diff.highlights[0]?.kind).toBe("changed");
    expect(diff.highlights[0]?.left).toContain("80%");
    expect(diff.highlights[0]?.right).toContain("85%");
  });

  it("marks added sentences on the right and removed on the left", () => {
    const left = "定义：平台是管控底座。";
    const right =
      "定义：平台是管控底座。\n\n新增能力：支持统一证书校验。";
    const diff = buildKnowledgeConflictDiff(left, right);
    expect(diff.rightSegments.some((segment) => segment.status === "added")).toBe(
      true,
    );
    expect(diff.highlights.some((item) => item.kind === "added")).toBe(true);
  });

  it("formats list subtitle with trigger source and first highlight", () => {
    const diff = buildKnowledgeConflictDiff(
      "磁盘使用率达到 80% 时告警。",
      "磁盘使用率达到 85% 时告警。",
    );
    const subtitle = buildConflictListSubtitle(
      "蓝鲸平台介绍.pptx",
      diff.highlights[0],
      labels,
    );
    expect(subtitle).toContain("蓝鲸平台介绍.pptx");
    expect(subtitle).toContain("80%");
    expect(subtitle).toContain("85%");
  });

  it("formats highlight labels", () => {
    expect(
      formatDiffHighlightLabel({ kind: "added", right: "新增一句说明。" }, labels),
    ).toContain("新增：");
    expect(
      formatDiffHighlightLabel(
        { kind: "removed", left: "旧的一句说明。" },
        labels,
      ),
    ).toContain("移除：");
  });
});
