export type WikiMarkdownImportFormat = "markdown" | "okf";

type Translate = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

export const OKF_FRONTMATTER_EXAMPLE = `---
type: concept
title: 页面标题
---`;

export interface MarkdownImportGovernanceErrorView {
  title: string;
  description?: string;
  example?: string;
}

export const markdownImportAccept = (
  importFormat: WikiMarkdownImportFormat = "markdown",
): string => (importFormat === "okf" ? ".zip" : ".md,.markdown,.zip");

export const markdownImportFilePattern = (
  importFormat: WikiMarkdownImportFormat = "markdown",
): RegExp =>
  importFormat === "okf" ? /\.zip$/iu : /\.(?:md|markdown|zip)$/iu;

export const initialCreateDirectoriesFromFolders = (
  importFormat: WikiMarkdownImportFormat = "markdown",
): boolean => importFormat === "okf";

const OKF_SKIP_REASON_KEYS: Record<string, string> = {
  reserved: "wiki.okfSkipReasonReserved",
  yaml_invalid: "wiki.okfSkipReasonYamlInvalid",
  type_missing: "wiki.okfSkipReasonTypeMissing",
  not_utf8: "wiki.okfSkipReasonNotUtf8",
};

export const okfSkippedReasonLabel = (
  t: Translate,
  reason: string,
): string => {
  const key = OKF_SKIP_REASON_KEYS[String(reason || "").trim()];
  if (key) return t(key);
  return interpolate(t("wiki.okfSkipReasonUnknown"), {
    reason: String(reason || "").trim() || "--",
  });
};

const interpolate = (
  template: string,
  values?: Record<string, string | number>,
) => {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) =>
    String(values[key] ?? `{${key}}`),
  );
};

const detailNumber = (
  details: unknown,
  key: string,
): number | undefined => {
  if (!details || typeof details !== "object") return undefined;
  const value = (details as Record<string, unknown>)[key];
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

export const formatArchiveBytes = (bytes?: number): string => {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return "--";
  if (bytes >= 1024 * 1024) {
    const mb = bytes / (1024 * 1024);
    return Number.isInteger(mb) ? `${mb} MB` : `${mb.toFixed(1)} MB`;
  }
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${Math.round(bytes)} B`;
};

const formatCount = (value?: number): string =>
  value == null ? "--" : String(value);

const sizedErrorView = (
  t: Translate,
  titleKey: string,
  descriptionKey: string,
  details: unknown,
  maxKey: string,
  actualKey: string,
  formatValue: (value?: number) => string = formatArchiveBytes,
): MarkdownImportGovernanceErrorView => ({
  title: t(titleKey),
  description: interpolate(t(descriptionKey), {
    max: formatValue(detailNumber(details, maxKey)),
    actual: formatValue(detailNumber(details, actualKey)),
  }),
});

const skippedReasons = (details: unknown): string[] => {
  if (!details || typeof details !== "object") return [];
  const skipped = (details as { skipped?: unknown }).skipped;
  if (!Array.isArray(skipped)) return [];
  return skipped.map((item) => {
    if (!item || typeof item !== "object") return "";
    return String((item as { reason?: unknown }).reason || "").trim();
  });
};

export const markdownImportGovernanceErrorView = (
  t: Translate,
  error: { code?: string; message?: string; details?: unknown },
): MarkdownImportGovernanceErrorView => {
  if (error.code === "okf_images_missing") {
    const details = error.details as
      | {
          missing?: { archive_path?: string; image_path?: string; reason?: string }[];
          truncated?: boolean;
          total?: number;
        }
      | undefined;
    const missing = Array.isArray(details?.missing) ? details.missing : [];
    const grouped = new Map<string, string[]>();
    for (const item of missing) {
      const archivePath = String(item?.archive_path || "").trim() || "--";
      const imagePath = String(item?.image_path || "").trim() || "--";
      const reasonKey = {
        not_found: "wiki.okfImageMissingNotFound",
        outside_bundle: "wiki.okfImageMissingOutside",
        not_image: "wiki.okfImageMissingNotImage",
        invalid_query: "wiki.okfImageMissingQuery",
      }[String(item?.reason || "")] || "wiki.okfImageMissingNotFound";
      const lines = grouped.get(archivePath) || [];
      lines.push(`${imagePath}（${t(reasonKey)}）`);
      grouped.set(archivePath, lines);
    }
    const blocks = [...grouped.entries()].map(
      ([path, lines]) => `${path}\n${lines.map((line) => `  ${line}`).join("\n")}`,
    );
    const extra =
      details?.truncated && (details.total || 0) > missing.length
        ? `\n${interpolate(t("wiki.okfImageMissingTruncated"), {
          count: (details.total || 0) - missing.length,
        })}`
        : "";
    return {
      title: t("wiki.okfImagesMissing"),
      description: `${t("wiki.okfImagesMissingDesc")}\n${blocks.join("\n")}${extra}`,
    };
  }
  if (error.code === "okf_no_concepts") {
    const reasons = new Set(skippedReasons(error.details));
    const description =
      reasons.has("type_missing") && !reasons.has("yaml_invalid")
        ? t("wiki.okfNoConceptsTypeMissing")
        : t("wiki.okfNoConceptsNeedFrontmatter");
    return {
      title: t("wiki.okfNoConcepts"),
      description,
      example: OKF_FRONTMATTER_EXAMPLE,
    };
  }
  if (error.code === "archive_empty") {
    return {
      title: t("wiki.archiveEmpty"),
      description: t("wiki.archiveEmptyDesc"),
    };
  }
  if (error.code === "archive_size_exceeded") {
    return sizedErrorView(
      t,
      "wiki.archiveTooLarge",
      "wiki.archiveTooLargeDesc",
      error.details,
      "max_bytes",
      "actual_bytes",
    );
  }
  if (error.code === "zip_file_size_limit") {
    return sizedErrorView(
      t,
      "wiki.zipFileTooLarge",
      "wiki.zipFileTooLargeDesc",
      error.details,
      "max_bytes",
      "actual_bytes",
    );
  }
  if (error.code === "zip_uncompressed_limit") {
    return sizedErrorView(
      t,
      "wiki.zipUncompressedTooLarge",
      "wiki.zipUncompressedTooLargeDesc",
      error.details,
      "max_bytes",
      "actual_bytes",
    );
  }
  if (error.code === "zip_entry_limit") {
    return sizedErrorView(
      t,
      "wiki.zipTooManyEntries",
      "wiki.zipTooManyEntriesDesc",
      error.details,
      "max_entries",
      "actual_entries",
      formatCount,
    );
  }
  return {
    title: error.message || t("wiki.markdownImportPreflightFailed"),
  };
};

export const formatMarkdownImportGovernanceError = (
  t: Translate,
  error: { code?: string; message?: string; details?: unknown },
): string => markdownImportGovernanceErrorView(t, error).title;
