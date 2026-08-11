export type SourceDataResult = { data: unknown; warnings: string[] };

export function unwrapSourceDataResponse(payload: unknown): SourceDataResult {
  if (
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload)
  ) {
    const obj = payload as { data?: unknown; warnings?: unknown };
    if (
      "data" in obj &&
      "warnings" in obj &&
      Array.isArray(obj.warnings)
    ) {
      return { data: obj.data, warnings: obj.warnings };
    }
  }
  return { data: payload, warnings: [] };
}
