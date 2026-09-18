interface ExportBlobError {
  message: string;
  code?: string;
}

const asBlob = (value: unknown): Blob | null =>
  typeof Blob !== "undefined" && value instanceof Blob ? value : null;

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" ? (value as Record<string, unknown>) : null;

const parseJsonErrorText = (text: string): ExportBlobError | null => {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const payload = JSON.parse(trimmed) as unknown;
    const record = asRecord(payload);
    const message =
      typeof record?.message === "string" ? record.message.trim() : "";
    if (!message) {
      return null;
    }
    return {
      message,
      code: typeof record?.code === "string" ? record.code : undefined,
    };
  } catch {
    return null;
  }
};

export const parseJsonErrorBlob = async (
  blob: Blob,
): Promise<ExportBlobError | null> => {
  const type = (blob.type || "").toLowerCase();
  if (type.includes("zip") || type.includes("octet-stream")) {
    return null;
  }
  if (blob.size > 64_000) {
    return null;
  }
  try {
    return parseJsonErrorText(await blob.text());
  } catch {
    return null;
  }
};

export const parseExportBlobError = async (
  error: unknown,
): Promise<ExportBlobError | null> => {
  const direct = asBlob(error);
  if (direct) {
    return parseJsonErrorBlob(direct);
  }
  const record = asRecord(error);
  const nested = [
    record?.payload,
    asRecord(record?.response)?.data,
  ];
  for (const candidate of nested) {
    const blob = asBlob(candidate);
    if (!blob) {
      continue;
    }
    const parsed = await parseJsonErrorBlob(blob);
    if (parsed) {
      return parsed;
    }
  }
  return null;
};
