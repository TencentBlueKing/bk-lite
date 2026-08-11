export interface SourceDataResult {
  data: unknown;
  warnings: string[];
}

export function parseSourceDataResponse(payload: unknown): SourceDataResult {
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
  throw new Error("统一取数响应格式无效");
}
