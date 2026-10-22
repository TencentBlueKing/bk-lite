import { afterEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import { sm2, sm4 } from "sm-crypto";
import {
  discardGmAxiosKey,
  gmFetch,
  invalidateGmTransportCache,
  loadGmPublic,
  openGmAxiosResponse,
  openResponseEnvelope,
  prepareGmAxiosRequest,
  resetGmTransportCache,
  sealRequestEnvelope,
  sealResponseEnvelope,
} from "@/utils/gmTransport";

const PRIVATE_KEY = "3945208F7B2144B13F36E38AC6D39F95889393692860B51A42FB81EF4DF7C5B8";
const PUBLIC_KEY = "09f9df311e5421a150dd7d161e4bc5c672179fad1833fc076bb08ff356f35020ccea490ce26775a52dc6ea718cc1aa600aed05fbf35e084a6632f6072da9ad13";
const KID = "3d92bed6d685f38b";
const SM4_KEY = Uint8Array.from(Buffer.from("0123456789abcdeffedcba9876543210", "hex"));
const REQUEST_IV = Uint8Array.from(Buffer.from("000102030405060708090a0b0c0d0e0f", "hex"));
const NONCE = "00112233445566778899aabbccddeeff";
const TS = 1760490000000;
const QUERY = "name=a&q=中文";
const BODY = new TextEncoder().encode('{"username":"admin"}');

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function publicPayload(data: Record<string, string>) {
  return jsonResponse({ result: true, data });
}

function ready(kid = KID) {
  return publicPayload({ enabled: "1", kid, public_key: PUBLIC_KEY });
}

afterEach(() => {
  resetGmTransportCache();
  vi.unstubAllGlobals();
});

describe("gmTransport", () => {
  it("matches the frozen request ciphertext and mac", () => {
    const envelope = sealRequestEnvelope({
      publicKey: PUBLIC_KEY,
      kid: KID,
      method: "POST",
      path: "/core/api/login/",
      cty: "application/json",
      query: QUERY,
      body: BODY,
      sm4Key: SM4_KEY,
      iv: REQUEST_IV,
      nonce: NONCE,
      ts: TS,
    });
    expect(envelope.iv).toBe("AAECAwQFBgcICQoLDA0ODw==");
    expect(envelope.ct).toBe("LmWdPuqenZzyexiGuwQ+ZqRpqA2XVRAOSXjuErGmJFcogC26JV9hJuv8kmmqNEuv");
    expect(envelope.mac).toBe("1vrjDrA/Qd5zCnO0ocOSzeWHZylXxF9fd88tvOeP+hA=");
    expect(String(envelope.ek)).not.toContain(PRIVATE_KEY);
  });

  it("opens an encrypted error response into the business payload", async () => {
    const envelope = sealResponseEnvelope({
      sm4Key: SM4_KEY,
      iv: Uint8Array.from(Buffer.from("0f0e0d0c0b0a09080706050403020100", "hex")),
      nonce: NONCE,
      seq: 1,
      status: 400,
      cty: "application/json",
      body: new TextEncoder().encode(JSON.stringify({ result: false, message: "名称已存在" })),
    });
    const config = { __gmKey: SM4_KEY, __gmNonce: NONCE };
    const response = await openGmAxiosResponse({
      status: 400,
      data: envelope,
      headers: axios.AxiosHeaders.from({ "X-Gm-Transport": "1" }),
      config,
    } as never);
    expect(response.data).toEqual({ result: false, message: "名称已存在" });
    expect(config.__gmKey).toBeUndefined();
  });

  it("drops the SM4 key when a transport error is plaintext", async () => {
    const config = { __gmKey: SM4_KEY, __gmNonce: NONCE };
    const response = await openGmAxiosResponse({
      status: 400,
      data: { result: false, code: "gm_transport_rejected", message: "请求被拒绝" },
      headers: axios.AxiosHeaders.from({ "Content-Type": "application/json" }),
      config,
    } as never);
    expect(response.data).toEqual({ result: false, code: "gm_transport_rejected", message: "请求被拒绝" });
    expect(config.__gmKey).toBeUndefined();
  });

  it("drops the SM4 key when the response mac does not match", async () => {
    const config = { __gmKey: SM4_KEY, __gmNonce: NONCE };
    const envelope = sealResponseEnvelope({
      sm4Key: SM4_KEY,
      iv: Uint8Array.from(Buffer.from("0f0e0d0c0b0a09080706050403020100", "hex")),
      nonce: NONCE,
      seq: 1,
      status: 200,
      cty: "application/json",
      body: new TextEncoder().encode('{"result":true}'),
    });
    envelope.mac = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
    await expect(openGmAxiosResponse({
      status: 200,
      data: envelope,
      headers: axios.AxiosHeaders.from({ "X-Gm-Transport": "1" }),
      config,
    } as never)).rejects.toThrow("gm response mac does not match");
    expect(config.__gmKey).toBeUndefined();
  });

  it("drops the SM4 key when a transport attempt has no response", () => {
    const config = { __gmKey: SM4_KEY };
    discardGmAxiosKey(config);
    expect(config.__gmKey).toBeUndefined();
  });

  it("does not keep a public key fetched before the switch was saved", async () => {
    let release: (value: Response) => void = () => undefined;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => gate));
    const first = loadGmPublic();
    invalidateGmTransportCache();
    release(ready());
    await expect(first).resolves.toEqual({ enabled: "1", kid: KID, publicKey: PUBLIC_KEY });

    let reads = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      reads += 1;
      return publicPayload({ enabled: "0" });
    }));
    await expect(loadGmPublic()).resolves.toEqual({ enabled: "0" });
    expect(reads).toBe(1);
  });

  it("opens the frozen response vector", () => {
    const plain = openResponseEnvelope(
      {
        v: 1,
        nonce: NONCE,
        seq: 1,
        status: 200,
        cty: "application/json",
        iv: "Dw4NDAsKCQgHBgUEAwIBAA==",
        ct: "kmvPmNfbk2kZvfR1L9V9Aw==",
        mac: "BwDX2gztEfzq3K/b6MP2VC+senzQS5cKH3W1xTSrezo=",
      },
      SM4_KEY,
      NONCE,
      200,
    );
    expect(new TextDecoder().decode(plain)).toBe('{"result":true}');
  });

  it("sends plaintext when the switch is off and does not cache a failed public read", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("gm_transport_public")) {
        return jsonResponse({ result: false }, 503);
      }
      return jsonResponse({ result: true, data: { ok: true } });
    }));
    const first = await gmFetch("/api/proxy/core/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"username":"admin"}',
    });
    const second = await gmFetch("/api/proxy/core/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"username":"admin"}',
    });
    expect(await first.json()).toEqual({ result: true, data: { ok: true } });
    expect(await second.json()).toEqual({ result: true, data: { ok: true } });
    expect(calls.filter((url) => url.includes("gm_transport_public"))).toHaveLength(2);
    expect(calls.filter((url) => url.endsWith("/login/"))).toHaveLength(2);
  });

  it("turns a switched-on GET into a POST envelope and returns plaintext", async () => {
    const sent: Array<{ url: string; method?: string; body?: string; headers?: Headers }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      sent.push({ url, method: init?.method, body: typeof init?.body === "string" ? init.body : undefined, headers: new Headers(init?.headers) });
      if (url.includes("gm_transport_public")) {
        return ready();
      }
      const envelope = JSON.parse(String(init?.body));
      const sm4Key = Uint8Array.from(sm2.doDecrypt(
        Buffer.from(envelope.ek, "base64").toString("hex"),
        PRIVATE_KEY,
        1,
        { output: "array" },
      ) as number[]);
      const response = sealResponseEnvelope({
        sm4Key,
        iv: REQUEST_IV,
        nonce: envelope.nonce,
        seq: 1,
        status: 200,
        cty: "application/json",
        body: new TextEncoder().encode('{"result":true,"data":{"page":1}}'),
      });
      return jsonResponse(response, 200, { "X-Gm-Transport": "1" });
    }));

    const response = await gmFetch("/api/proxy/cmdb/api/instances/?page=1&q=%E4%B8%AD%E6%96%87", { method: "GET" });
    expect(await response.json()).toEqual({ result: true, data: { page: 1 } });
    expect(response.headers.get("X-Gm-Transport")).toBeNull();
    const business = sent.filter((item) => item.url.includes("/cmdb/"));
    expect(business).toHaveLength(1);
    expect(business[0].method).toBe("POST");
    expect(business[0].url).toBe("/api/proxy/cmdb/api/instances/");
    expect(business[0].headers?.get("X-Gm-Transport")).toBe("1");
    const envelope = JSON.parse(business[0].body || "");
    expect(envelope.method).toBe("GET");
    expect(envelope.path).toBe("/cmdb/api/instances/");
    const sm4Key = Uint8Array.from(sm2.doDecrypt(
      Buffer.from(envelope.ek, "base64").toString("hex"),
      PRIVATE_KEY,
      1,
      { output: "array" },
    ) as number[]);
    const plain = sm4.decrypt(Array.from(Buffer.from(envelope.ct, "base64")), Buffer.from(sm4Key).toString("hex"), {
      mode: "cbc",
      iv: Buffer.from(envelope.iv, "base64").toString("hex"),
      output: "array",
    }) as number[];
    const framed = Uint8Array.from(plain);
    const queryLength = new DataView(framed.buffer, framed.byteOffset, framed.byteLength).getUint32(0);
    expect(new TextDecoder().decode(framed.slice(4, 4 + queryLength))).toBe("page=1&q=%E4%B8%AD%E6%96%87");
  });

  it("leaves file uploads and event streams unencrypted", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return jsonResponse({ result: true });
    }));
    await gmFetch("/api/proxy/cmdb/api/model/import_model_config/", { method: "POST", body: new FormData() });
    await gmFetch("/api/proxy/opspilot/bot_mgmt/chat/", {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      body: "{}",
    });
    expect(calls.some((url) => url.includes("gm_transport_public"))).toBe(false);
    expect(calls).toHaveLength(2);
  });

  it("shares one public request across concurrent callers and uses a new nonce on retry", async () => {
    let publicReads = 0;
    const nonces: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("gm_transport_public")) {
        publicReads += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return publicReads === 1 ? ready() : ready("aaaaaaaaaaaaaaaa");
      }
      const envelope = JSON.parse(String(init?.body));
      nonces.push(envelope.nonce);
      if (nonces.length === 1) {
        return jsonResponse({ result: false, code: "gm_transport_unavailable" }, 503);
      }
      return jsonResponse({ result: true });
    }));
    await Promise.all([
      loadGmPublic(),
      loadGmPublic(),
    ]);
    expect(publicReads).toBe(1);
    await gmFetch("/api/proxy/core/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    expect(nonces).toHaveLength(2);
    expect(nonces[0]).not.toBe(nonces[1]);
    expect(publicReads).toBe(2);
  });

  it("does not resend a rejected envelope when the key id is unchanged", async () => {
    const business: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("gm_transport_public")) {
        return ready();
      }
      business.push(String(init?.body));
      return jsonResponse({ result: false, code: "gm_transport_rejected" }, 400);
    }));
    const response = await gmFetch("/api/proxy/core/api/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    expect(response.status).toBe(400);
    expect(business).toHaveLength(1);
  });

  it("drops the transport header when a retry finds encryption off", async () => {
    let reads = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      reads += 1;
      return reads === 1 ? ready() : publicPayload({ enabled: "0" });
    }));
    const config = await prepareGmAxiosRequest({
      baseURL: "/api/proxy",
      url: "core/api/login/",
      method: "post",
      data: { username: "admin" },
      headers: axios.AxiosHeaders.from({ "Content-Type": "application/json" }),
    } as never);
    expect(config.headers.get("X-Gm-Transport")).toBe("1");
    invalidateGmTransportCache();
    const again = await prepareGmAxiosRequest(config);
    expect(again.headers.get("X-Gm-Transport")).toBeUndefined();
    expect(again.data).toEqual({ username: "admin" });
    expect(String(again.method).toLowerCase()).toBe("post");
  });

  it("keeps an axios blob download and reseals a retried json request", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ready()));
    const blobConfig = await prepareGmAxiosRequest({
      baseURL: "/api/proxy",
      url: "cmdb/api/change_record/export/",
      method: "get",
      responseType: "blob",
      headers: axios.AxiosHeaders.from({}),
    } as never);
    expect(blobConfig.method).toBe("get");
    expect(blobConfig.responseType).toBe("blob");

    const jsonConfig = await prepareGmAxiosRequest({
      baseURL: "/api/proxy",
      url: "core/api/login/",
      method: "post",
      data: { username: "admin" },
      headers: axios.AxiosHeaders.from({ "Content-Type": "application/json" }),
    } as never);
    const firstNonce = (jsonConfig.data as { nonce: string }).nonce;
    jsonConfig.__gmRetried = false;
    const again = await prepareGmAxiosRequest(jsonConfig);
    expect((again.data as { nonce: string }).nonce).not.toBe(firstNonce);
    expect(again.data).toMatchObject({ method: "POST", path: "/core/api/login/" });
  });
});
