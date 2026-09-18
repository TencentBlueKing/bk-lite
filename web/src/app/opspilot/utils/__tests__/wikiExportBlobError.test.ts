import { describe, expect, it } from "vitest";
import {
  parseExportBlobError,
  parseJsonErrorBlob,
} from "../wikiExportBlobError";

describe("parseJsonErrorBlob", () => {
  it("reads message and code from a JSON error blob", async () => {
    const blob = new Blob(
      [JSON.stringify({ result: false, code: "max_bytes", message: "导出内容超过 200 MB 上限,已停止" })],
      { type: "application/json" },
    );
    await expect(parseJsonErrorBlob(blob)).resolves.toEqual({
      message: "导出内容超过 200 MB 上限,已停止",
      code: "max_bytes",
    });
  });

  it("does not treat a zip blob as an error payload", async () => {
    const blob = new Blob([new Uint8Array([0x50, 0x4b])], {
      type: "application/zip",
    });
    await expect(parseJsonErrorBlob(blob)).resolves.toBeNull();
  });
});

describe("parseExportBlobError", () => {
  it("reads a HandledRequestError-style payload blob", async () => {
    const payload = new Blob(
      [JSON.stringify({ message: "已就绪知识库缺少 active generation", code: "active_generation_missing" })],
      { type: "application/json" },
    );
    await expect(parseExportBlobError({ payload })).resolves.toEqual({
      message: "已就绪知识库缺少 active generation",
      code: "active_generation_missing",
    });
  });
});
