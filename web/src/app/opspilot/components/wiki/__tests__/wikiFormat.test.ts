import { describe, expect, it } from "vitest";
import {
  formatPageTypeLabel,
  formatWikiTagLabel,
  pageTypeSelectOption,
} from "../wikiFormat";

const t = (
  id: string,
  _defaultMessage?: string,
  values?: Record<string, string | number>,
) => {
  const messages: Record<string, string> = {
    "wiki.pageTypeQuery": "待研究问题",
    "wiki.pageTypeEntity": "实体",
    "wiki.tagOkfUnverified": "未核验",
    "wiki.tagOkfHumanReviewed": "人工核验",
    "wiki.tagOkfType": "OKF 类型：{type}",
  };
  const template = messages[id] || id;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) =>
    String(values[key] ?? `{${key}}`),
  );
};

describe("formatPageTypeLabel", () => {
  it("maps catalog keys to i18n labels", () => {
    expect(formatPageTypeLabel(t, "query")).toBe("待研究问题");
    expect(formatPageTypeLabel(t, "ENTITY")).toBe("实体");
  });

  it("keeps unknown types as entered", () => {
    expect(formatPageTypeLabel(t, "custom_type")).toBe("custom_type");
  });

  it("keeps select values as keys", () => {
    expect(pageTypeSelectOption(t, "query")).toEqual({
      value: "query",
      label: "待研究问题",
    });
  });
});

describe("formatWikiTagLabel", () => {
  it("maps importer system tags to i18n labels", () => {
    expect(formatWikiTagLabel(t, "okf:unverified")).toBe("未核验");
    expect(formatWikiTagLabel(t, "OKF:human_reviewed")).toBe("人工核验");
  });

  it("formats unmatched OKF type tags", () => {
    expect(formatWikiTagLabel(t, "okf:BigQuery Table")).toBe(
      "OKF 类型：BigQuery Table",
    );
  });

  it("keeps document or LLM tags as entered", () => {
    expect(formatWikiTagLabel(t, "architecture")).toBe("architecture");
  });
});
