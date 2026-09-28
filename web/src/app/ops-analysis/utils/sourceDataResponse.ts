export interface SourceDataResult {
  data: unknown;
  warnings: string[];
}

export type SourceDataMessage = (id: string, defaultMessage?: string) => string;

const formatSourceDataFallback: SourceDataMessage = (id, defaultMessage) =>
  defaultMessage ?? id;

export function parseSourceDataResponse(
  payload: unknown,
  translate?: SourceDataMessage,
): SourceDataResult {
  const t: SourceDataMessage = translate ?? formatSourceDataFallback;
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
    t("dashboard.invalidSourceDataResponse", "统一取数响应格式无效"),
  );
}
