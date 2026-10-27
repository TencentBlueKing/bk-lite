import { existsSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { gmTransportAvailable, selectGmTransport } from "@/utils/gmTransport";

describe("gmTransport community seam", () => {
  it("stays plaintext when the enterprise module is absent", async () => {
    const api = selectGmTransport(null);
    expect(api.available).toBe(false);
    const fetchMock = vi.fn(async () => new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    const response = await api.gmFetch("/api/proxy/core/api/login/", {
      method: "POST",
      body: "{}",
    });
    expect(await response.text()).toBe("ok");
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/core/api/login/", {
      method: "POST",
      body: "{}",
    });
    const config = { url: "core/api/login/", method: "get" };
    await expect(api.prepareGmAxiosRequest(config as never)).resolves.toBe(config);
    await expect(api.openGmAxiosResponse({ data: { ok: true } } as never)).resolves.toEqual({ data: { ok: true } });
    await expect(api.retryGmAxiosRequest({})).resolves.toBe(false);
    vi.unstubAllGlobals();
  });

  it("follows whether the enterprise module is on disk", () => {
    const present = existsSync(
      new URL("../../app/system-manager/(enterprise)/utils/gmTransport.ts", import.meta.url),
    );
    expect(gmTransportAvailable).toBe(present);
  });
});
