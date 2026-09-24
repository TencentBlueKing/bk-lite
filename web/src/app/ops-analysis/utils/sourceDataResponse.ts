export interface SourceDataResult {
  data: unknown;
  warnings: string[];
}

export type SourceDataMessage = (id: string, defaultMessage?: string) => string;

export function parseSourceDataResponse(
  payload: unknown,
  t?: SourceDataMessage,
): SourceDataResult {
  if (
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload)
  ) {
    const obj = payload as { data?: unknown; warnings?: unknown };
    if (
      "data" in obj &&
      "warnings" in obj &&
      Array.isArray(obj.warnings) &&
      obj.warnings.every((warning) => typeof warning === "string")
    ) {
      return { data: obj.data, warnings: obj.warnings };
    }
  }
  throw new Error(
    t
      ? t("dashboard.invalidSourceDataResponse", "统一取数响应格式无效")
      : "统一取数响应格式无效",
  );
}
