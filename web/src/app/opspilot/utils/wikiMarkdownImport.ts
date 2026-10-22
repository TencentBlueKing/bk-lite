import type { WikiMarkdownImportExecuteResult } from "@/app/opspilot/types/wiki";

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

export const markdownImportAccept = (): string => ".zip";

export const markdownImportFilePattern = (): RegExp => /\.zip$/iu;

export const initialCreateDirectoriesFromFolders = (): boolean => false;

const OKF_SKIP_REASON_KEYS: Record<string, string> = {
  reserved: "wiki.okfSkipReasonReserved",
  yaml_invalid: "wiki.okfSkipReasonYamlInvalid",
  type_missing: "wiki.okfSkipReasonTypeMissing",
  not_utf8: "wiki.okfSkipReasonNotUtf8",
  images_missing: "wiki.okfSkipReasonImagesMissing",
  title_invalid: "wiki.okfSkipReasonTitleInvalid",
  title_duplicate: "wiki.okfSkipReasonTitleDuplicate",
  import_failed: "wiki.okfSkipReasonImportFailed",
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

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const hasMarkdownImportResultFields = (row: Record<string, unknown>): boolean =>
  row.async !== undefined ||
  row.accepted !== undefined ||
  row.queued !== undefined ||
  row.build_record_id !== undefined ||
  row.generation_id !== undefined ||
  row.counts !== undefined ||
  row.pages !== undefined ||
  row.created !== undefined ||
  row.updated !== undefined;

export const unwrapMarkdownImportExecuteResult = (
  raw: unknown,
): WikiMarkdownImportExecuteResult => {
  let current: unknown = raw;
  for (let depth = 0; depth < 3; depth += 1) {
    if (!isPlainObject(current)) return {};
    if (hasMarkdownImportResultFields(current)) {
      return current as WikiMarkdownImportExecuteResult;
    }
    if (isPlainObject(current.data)) {
      current = current.data;
      continue;
    }
    return current as WikiMarkdownImportExecuteResult;
  }
  return isPlainObject(current)
    ? (current as WikiMarkdownImportExecuteResult)
    : {};
};

export const isBackgroundMarkdownImport = (
  result: WikiMarkdownImportExecuteResult,
): boolean => {
  if (result.queued === true || result.accepted === true || result.async === true) {
    return true;
  }
  if (result.build_record_id == null) return false;
  if (result.generation_id != null || result.pages != null) return false;
  const status = String(result.status || "");
  const stage = String(result.stage || "");
  if (status === "running" || status === "queued" || stage === "queued") {
    return true;
  }
  return result.counts == null;
};

/** 后台受理后若一直看不到运行中或终态，到点放开导入/导出。 */
export const OKF_IMPORT_HOLD_TIMEOUT_MS = 45 * 60 * 1000;

const OKF_IMPORT_ENRICH_FRESH_MS = 2 * 60 * 60 * 1000;
const OKF_IMPORT_HOLD_MATCH_SKEW_MS = 60 * 1000;

const OKF_IMPORT_FAILURE_STATUSES = new Set([
  "failed",
  "cancelled",
  "canceled",
  "partial",
]);

export interface OkfImportAcceptance {
  buildRecordId?: number;
  status?: string;
}

export interface OkfImportBuildSnapshot {
  id?: number;
  status?: string;
  progress?: number;
  updated_at?: string;
  maintenance?: object | null;
}

export type OkfImportProgressPhase =
  | { phase: "writing"; progress: number }
  | { phase: "enriching" }
  | { phase: "holding" }
  | { phase: "completed"; outcome: "success" | "failed" }
  | { phase: "idle" };

export interface ResolveOkfImportProgressInput {
  items: OkfImportBuildSnapshot[];
  trackedBuildRecordId?: number | null;
  acceptedStatus?: string | null;
  holding: boolean;
  holdStartedAt?: number | null;
  seenActive: boolean;
  now: number;
}

const normalizeImportStatus = (status?: string | null): string =>
  String(status || "").trim().toLowerCase();

const isActiveImportStatus = (status: string): boolean =>
  status === "running" || status === "queued";

const writingProgress = (progress?: number): number =>
  Math.min(99, Math.max(0, Number(progress) || 0));

const snapshotUpdatedAt = (item: OkfImportBuildSnapshot): number | null => {
  const parsed = Date.parse(item.updated_at || "");
  return Number.isFinite(parsed) ? parsed : null;
};

export const okfImportHoldTimedOut = (
  holdStartedAt: number | null | undefined,
  now: number,
  holding: boolean,
): boolean =>
  holding &&
  holdStartedAt != null &&
  now - holdStartedAt >= OKF_IMPORT_HOLD_TIMEOUT_MS;

const searchEnrichmentState = (item: OkfImportBuildSnapshot): unknown => {
  const maintenance = item.maintenance;
  if (!maintenance || typeof maintenance !== "object") return undefined;
  return (maintenance as { search_enrichment?: unknown }).search_enrichment;
};

const enrichmentStillRunning = (
  item: OkfImportBuildSnapshot,
  now: number,
): boolean => {
  if (searchEnrichmentState(item) !== "running") return false;
  const updated = snapshotUpdatedAt(item);
  return updated == null || now - updated < OKF_IMPORT_ENRICH_FRESH_MS;
};

const phaseForImportRecord = (
  item: OkfImportBuildSnapshot,
  now: number,
): OkfImportProgressPhase | null => {
  const status = normalizeImportStatus(item.status);
  if (isActiveImportStatus(status)) {
    return { phase: "writing", progress: writingProgress(item.progress) };
  }
  if (
    enrichmentStillRunning(item, now) &&
    (status === "success" || status === "partial" || status === "")
  ) {
    return { phase: "enriching" };
  }
  if (status === "success") {
    return { phase: "completed", outcome: "success" };
  }
  if (OKF_IMPORT_FAILURE_STATUSES.has(status)) {
    return { phase: "completed", outcome: "failed" };
  }
  return null;
};

const newestTerminalSinceHold = (
  items: OkfImportBuildSnapshot[],
  holdStartedAt: number,
): OkfImportBuildSnapshot | null => {
  const cutoff = holdStartedAt - OKF_IMPORT_HOLD_MATCH_SKEW_MS;
  const matches = items.filter((item) => {
    const status = normalizeImportStatus(item.status);
    if (status !== "success" && !OKF_IMPORT_FAILURE_STATUSES.has(status)) {
      return false;
    }
    const updated = snapshotUpdatedAt(item);
    return updated != null && updated >= cutoff;
  });
  matches.sort(
    (left, right) =>
      (snapshotUpdatedAt(right) || 0) - (snapshotUpdatedAt(left) || 0),
  );
  return matches[0] ?? null;
};

export const resolveOkfImportProgress = (
  input: ResolveOkfImportProgressInput,
): OkfImportProgressPhase => {
  const trackedId = input.trackedBuildRecordId ?? null;
  if (trackedId != null) {
    const tracked = input.items.find((item) => item.id === trackedId);
    if (tracked) {
      const phase = phaseForImportRecord(tracked, input.now);
      if (phase) return phase;
      if (okfImportHoldTimedOut(input.holdStartedAt, input.now, input.holding)) {
        return { phase: "completed", outcome: "failed" };
      }
      if (input.holding || input.seenActive) return { phase: "holding" };
      return { phase: "idle" };
    }
    const accepted = normalizeImportStatus(input.acceptedStatus);
    if (OKF_IMPORT_FAILURE_STATUSES.has(accepted)) {
      return { phase: "completed", outcome: "failed" };
    }
  } else {
    const writing = input.items.find((item) =>
      isActiveImportStatus(normalizeImportStatus(item.status)),
    );
    if (writing) {
      return { phase: "writing", progress: writingProgress(writing.progress) };
    }
    const enriching = input.items.find((item) =>
      enrichmentStillRunning(item, input.now),
    );
    if (enriching) return { phase: "enriching" };
    if (input.seenActive) {
      return { phase: "completed", outcome: "success" };
    }
    if (input.holding && input.holdStartedAt != null) {
      const matched = newestTerminalSinceHold(input.items, input.holdStartedAt);
      if (matched) {
        const phase = phaseForImportRecord(matched, input.now);
        if (phase) return phase;
      }
    }
  }

  if (okfImportHoldTimedOut(input.holdStartedAt, input.now, input.holding)) {
    return { phase: "completed", outcome: "failed" };
  }
  if (input.holding) return { phase: "holding" };
  if (trackedId != null && input.seenActive) {
    return { phase: "completed", outcome: "success" };
  }
  return { phase: "idle" };
};
