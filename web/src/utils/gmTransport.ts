import axios, { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { sm2, sm3, sm4 } from "sm-crypto";

const PUBLIC_PATH = "/api/proxy/core/api/gm_transport_public/";
const CACHE_TTL_MS = 5 * 60 * 1000;
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

export type GmPublic =
  | { enabled: "0"; degraded?: "1" }
  | { enabled: "1"; kid: string; publicKey: string };

export type GmAxiosConfig = InternalAxiosRequestConfig & {
  __gmOriginal?: {
    method?: string;
    url?: string;
    data?: unknown;
    params?: unknown;
    baseURL?: string;
  };
  __gmKey?: Uint8Array;
  __gmNonce?: string;
  __gmKid?: string;
  __gmRetried?: boolean;
};

type Envelope = Record<string, unknown>;

let cached: { at: number; value: GmPublic } | null = null;
let inflight: Promise<GmPublic> | null = null;
let generation = 0;

function dropGmPublicCache(): void {
  generation += 1;
  cached = null;
  inflight = null;
}

export function resetGmTransportCache(): void {
  dropGmPublicCache();
}

export function invalidateGmTransportCache(): void {
  dropGmPublicCache();
}

export async function loadGmPublic(force = false): Promise<GmPublic> {
  if (!force && cached && Date.now() - cached.at < CACHE_TTL_MS) {
    return cached.value;
  }
  if (!force && inflight) {
    return inflight;
  }
  const ticket = generation;
  const pending = (async () => {
    try {
      const value = await fetchPublic();
      if (ticket === generation) {
        cached = { at: Date.now(), value };
      }
      return value;
    } catch {
      return { enabled: "0" } as GmPublic;
    } finally {
      if (inflight === pending) {
        inflight = null;
      }
    }
  })();
  inflight = pending;
  return pending;
}

export function sealRequestEnvelope(input: {
  publicKey: string;
  kid: string;
  method: string;
  path: string;
  cty: string;
  query: string;
  body: Uint8Array;
  sm4Key: Uint8Array;
  iv: Uint8Array;
  nonce: string;
  ts: number;
}): Envelope {
  const ivB64 = bytesToBase64(input.iv);
  const ciphertext = sm4.encrypt(Array.from(framePlaintext(input.query, input.body)), bytesToHex(input.sm4Key), {
    mode: "cbc",
    iv: bytesToHex(input.iv),
    output: "array",
  }) as number[];
  const ctB64 = bytesToBase64(Uint8Array.from(ciphertext));
  const mac = macBase64(
    input.sm4Key,
    requestMac(input.ts, input.nonce, input.method, input.path, input.cty, ivB64, ctB64),
  );
  const ek = bytesToBase64(hexToBytes(sm2.doEncrypt(Array.from(input.sm4Key), sm2PublicKey(input.publicKey), 1)));
  return {
    v: 1,
    ts: input.ts,
    nonce: input.nonce,
    kid: input.kid,
    method: input.method,
    path: input.path,
    cty: input.cty,
    ek,
    iv: ivB64,
    ct: ctB64,
    mac,
  };
}

export function sealResponseEnvelope(input: {
  sm4Key: Uint8Array;
  iv: Uint8Array;
  nonce: string;
  seq: number;
  status: number;
  cty: string;
  body: Uint8Array;
}): Envelope {
  const ivB64 = bytesToBase64(input.iv);
  const ciphertext = sm4.encrypt(Array.from(input.body), bytesToHex(input.sm4Key), {
    mode: "cbc",
    iv: bytesToHex(input.iv),
    output: "array",
  }) as number[];
  const ctB64 = bytesToBase64(Uint8Array.from(ciphertext));
  return {
    v: 1,
    nonce: input.nonce,
    seq: input.seq,
    status: input.status,
    cty: input.cty,
    iv: ivB64,
    ct: ctB64,
    mac: macBase64(input.sm4Key, responseMac(input.nonce, input.seq, input.status, input.cty, ivB64, ctB64)),
  };
}

export function openResponseEnvelope(envelope: Envelope, sm4Key: Uint8Array, nonce: string, status: number): Uint8Array<ArrayBuffer> {
  if (envelope.v !== 1 || envelope.nonce !== nonce || envelope.seq !== 1 || envelope.status !== status) {
    throw new Error("gm response does not match this request");
  }
  const ivB64 = String(envelope.iv || "");
  const ctB64 = String(envelope.ct || "");
  const cty = String(envelope.cty || "");
  const expected = sm3(Array.from(responseMac(nonce, 1, status, cty, ivB64, ctB64)), { key: Array.from(sm4Key) });
  if (!macMatches(expected, String(envelope.mac || ""))) {
    throw new Error("gm response mac does not match");
  }
  const plain = sm4.decrypt(Array.from(base64ToBytes(ctB64)), bytesToHex(sm4Key), {
    mode: "cbc",
    iv: bytesToHex(base64ToBytes(ivB64)),
    output: "array",
  }) as number[];
  return Uint8Array.from(plain);
}

export async function prepareGmAxiosRequest(config: GmAxiosConfig): Promise<GmAxiosConfig> {
  if (shouldSkipAxios(config)) {
    return config;
  }
  if (!config.__gmOriginal) {
    config.__gmOriginal = {
      method: config.method,
      url: config.url,
      data: config.data,
      params: config.params,
      baseURL: config.baseURL,
    };
  } else {
    config.method = config.__gmOriginal.method;
    config.url = config.__gmOriginal.url;
    config.data = config.__gmOriginal.data;
    config.params = config.__gmOriginal.params as InternalAxiosRequestConfig["params"];
    config.baseURL = config.__gmOriginal.baseURL;
    discardGmAxiosKey(config);
  }
  const material = await loadGmPublic();
  if (material.enabled !== "1") {
    deleteHeader(config.headers, "X-Gm-Transport");
    return config;
  }
  const href = axios.getUri(config);
  const target = splitProxyUrl(href);
  const method = (config.method || "get").toUpperCase();
  const cty = contentTypeOf(config) || (isJsonBody(config.data) ? "application/json" : "application/octet-stream");
  const sm4Key = randomBytes(16);
  const iv = randomBytes(16);
  const nonce = bytesToHex(randomBytes(16));
  const envelope = sealRequestEnvelope({
    publicKey: material.publicKey,
    kid: material.kid,
    method,
    path: target.path,
    cty,
    query: target.query,
    body: bodyBytes(config.data),
    sm4Key,
    iv,
    nonce,
    ts: Date.now(),
  });
  config.baseURL = "/api/proxy";
  config.url = target.path.replace(/^\//, "");
  config.params = undefined;
  config.data = envelope;
  if (method === "GET") {
    config.method = "post";
  }
  setHeader(config.headers, "Content-Type", "application/json");
  setHeader(config.headers, "X-Gm-Transport", "1");
  config.__gmKey = sm4Key;
  config.__gmNonce = nonce;
  config.__gmKid = material.kid;
  return config;
}

export function discardGmAxiosKey(config?: GmAxiosConfig | null): void {
  if (config) {
    delete config.__gmKey;
  }
}

export async function openGmAxiosResponse(response: AxiosResponse): Promise<AxiosResponse> {
  const config = response.config as GmAxiosConfig | undefined;
  try {
    if (!config?.__gmKey || !hasTransportHeader(response.headers)) {
      return response;
    }
    const envelope = typeof response.data === "string" ? JSON.parse(response.data) : response.data;
    const plain = openResponseEnvelope(envelope, config.__gmKey, config.__gmNonce || "", response.status);
    const cty = String(envelope.cty || "application/json");
    response.data = cty.includes("json") ? JSON.parse(textDecoder.decode(plain)) : textDecoder.decode(plain);
    setHeader(response.headers, "Content-Type", cty);
    return response;
  } finally {
    discardGmAxiosKey(config);
  }
}

export async function retryGmAxiosRequest(error: { config?: GmAxiosConfig; response?: { status?: number; data?: { code?: string } } }): Promise<boolean> {
  const config = error.config;
  const code = error.response?.data?.code;
  if (!config || config.__gmRetried || !config.__gmKid) {
    return false;
  }
  if (code !== "gm_transport_unavailable" && code !== "gm_transport_rejected") {
    return false;
  }
  const previousKid = config.__gmKid;
  invalidateGmTransportCache();
  const material = await loadGmPublic(true);
  const kidChanged = material.enabled === "1" && material.kid !== previousKid;
  if (code === "gm_transport_rejected" && !kidChanged) {
    return false;
  }
  config.__gmRetried = true;
  return true;
}

export async function gmFetch(input: RequestInfo | URL, init: RequestInit = {}, retried = false): Promise<Response> {
  const method = (init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
  const url = input instanceof Request ? input.url : String(input);
  const headers = new Headers(input instanceof Request ? input.headers : undefined);
  if (init.headers) {
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  }
  if (!shouldSealFetch(url, method, headers, init.body)) {
    return fetch(input, init);
  }
  const material = await loadGmPublic();
  if (material.enabled !== "1") {
    return fetch(input, init);
  }
  const target = splitProxyUrl(url);
  const cty = headers.get("Content-Type") || "application/octet-stream";
  const body = await readBody(init.body ?? (input instanceof Request ? input.clone().body : null));
  const sm4Key = randomBytes(16);
  const nonce = bytesToHex(randomBytes(16));
  const envelope = sealRequestEnvelope({
    publicKey: material.publicKey,
    kid: material.kid,
    method,
    path: target.path,
    cty,
    query: target.query,
    body,
    sm4Key,
    iv: randomBytes(16),
    nonce,
    ts: Date.now(),
  });
  headers.set("Content-Type", "application/json");
  headers.set("X-Gm-Transport", "1");
  const wireMethod = method === "GET" ? "POST" : method;
  const response = await fetch(proxyUrl(target.path), {
    method: wireMethod,
    headers,
    body: JSON.stringify(envelope),
    signal: init.signal,
    credentials: init.credentials,
  });
  const raw = await response.text();
  if (!response.headers.get("X-Gm-Transport")) {
    if (!retried) {
      const payload = parseJson(raw) as { code?: string } | null;
      if (payload?.code === "gm_transport_unavailable" || payload?.code === "gm_transport_rejected") {
        invalidateGmTransportCache();
        const next = await loadGmPublic(true);
        const kidChanged = next.enabled === "1" && next.kid !== material.kid;
        if (payload.code === "gm_transport_unavailable" || kidChanged) {
          if (next.enabled !== "1") {
            return fetch(input, init);
          }
          return gmFetch(input, init, true);
        }
      }
    }
    return new Response(raw, { status: response.status, statusText: response.statusText, headers: response.headers });
  }
  const envelopeBody = JSON.parse(raw) as Envelope;
  const opened = openResponseEnvelope(envelopeBody, sm4Key, nonce, response.status);
  const nextHeaders = new Headers(response.headers);
  nextHeaders.set("Content-Type", String(envelopeBody.cty || cty));
  nextHeaders.delete("X-Gm-Transport");
  return new Response(opened, { status: response.status, statusText: response.statusText, headers: nextHeaders });
}

async function fetchPublic(): Promise<GmPublic> {
  const response = await fetch(PUBLIC_PATH, { method: "GET" });
  if (!response.ok) {
    throw new Error("gm public status failed");
  }
  const payload = await response.json();
  const data = payload?.data;
  if (!data || (data.enabled !== "0" && data.enabled !== "1")) {
    throw new Error("gm public status is invalid");
  }
  if (data.enabled !== "1") {
    return data.degraded === "1" ? { enabled: "0", degraded: "1" } : { enabled: "0" };
  }
  if (typeof data.public_key !== "string" || typeof data.kid !== "string") {
    throw new Error("gm public key is missing");
  }
  return { enabled: "1", kid: data.kid, publicKey: data.public_key };
}

function shouldSkipAxios(config: GmAxiosConfig): boolean {
  const method = (config.method || "get").toUpperCase();
  if (method === "HEAD") {
    return true;
  }
  if (config.responseType === "blob" || config.responseType === "arraybuffer" || config.responseType === "stream") {
    return true;
  }
  if (headerValue(config.headers, "Accept").includes("text/event-stream")) {
    return true;
  }
  if (isBinaryBody(config.data)) {
    return true;
  }
  const href = axios.getUri(config);
  return splitProxyUrl(href).path.replace(/\/$/, "") === "/core/api/gm_transport_public";
}

function shouldSealFetch(url: string, method: string, headers: Headers, body: BodyInit | null | undefined): boolean {
  const parsed = new URL(url, "http://gm.local");
  if (!parsed.pathname.startsWith("/api/proxy/")) {
    return false;
  }
  if (parsed.pathname.replace(/\/$/, "").endsWith("/core/api/gm_transport_public")) {
    return false;
  }
  if (method === "HEAD") {
    return false;
  }
  if ((headers.get("Accept") || "").includes("text/event-stream")) {
    return false;
  }
  return !isBinaryBody(body);
}

async function readBody(body: BodyInit | null | undefined): Promise<Uint8Array> {
  if (body == null) {
    return new Uint8Array();
  }
  if (typeof body === "string") {
    return textEncoder.encode(body);
  }
  if (body instanceof URLSearchParams) {
    return textEncoder.encode(body.toString());
  }
  if (body instanceof ArrayBuffer) {
    return new Uint8Array(body);
  }
  if (ArrayBuffer.isView(body)) {
    return new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
  }
  const buffer = await new Response(body).arrayBuffer();
  return new Uint8Array(buffer);
}

function parseJson(raw: string): unknown {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function splitProxyUrl(href: string): { path: string; query: string } {
  const parsed = new URL(href, "http://gm.local");
  let path = parsed.pathname;
  if (path.startsWith("/api/proxy")) {
    path = path.slice("/api/proxy".length);
  }
  if (!path.startsWith("/")) {
    path = `/${path}`;
  }
  if (!path.endsWith("/")) {
    path = `${path}/`;
  }
  return { path, query: parsed.search.startsWith("?") ? parsed.search.slice(1) : parsed.search };
}

function proxyUrl(path: string): string {
  return `/api/proxy${path}`;
}

function framePlaintext(query: string, body: Uint8Array): Uint8Array {
  const queryBytes = textEncoder.encode(query);
  const framed = new Uint8Array(4 + queryBytes.length + body.length);
  new DataView(framed.buffer).setUint32(0, queryBytes.length);
  framed.set(queryBytes, 4);
  framed.set(body, 4 + queryBytes.length);
  return framed;
}

function requestMac(ts: number, nonce: string, method: string, path: string, cty: string, ivB64: string, ctB64: string): Uint8Array {
  return textEncoder.encode(["1", String(ts), nonce, method, path, cty, ivB64, ctB64].join("\n"));
}

function responseMac(nonce: string, seq: number, status: number, cty: string, ivB64: string, ctB64: string): Uint8Array {
  return textEncoder.encode(["1", "resp", nonce, String(seq), String(status), cty, ivB64, ctB64].join("\n"));
}

function macBase64(key: Uint8Array, message: Uint8Array): string {
  return bytesToBase64(hexToBytes(sm3(Array.from(message), { key: Array.from(key) })));
}

function macMatches(expectedHex: string, actualB64: string): boolean {
  const actual = bytesToHex(base64ToBytes(actualB64));
  if (expectedHex.length !== actual.length) {
    return false;
  }
  let diff = 0;
  for (let index = 0; index < expectedHex.length; index += 1) {
    diff |= expectedHex.charCodeAt(index) ^ actual.charCodeAt(index);
  }
  return diff === 0;
}

function sm2PublicKey(publicKey: string): string {
  return publicKey.length === 128 ? `04${publicKey}` : publicKey;
}

function bodyBytes(data: unknown): Uint8Array {
  if (data == null) {
    return new Uint8Array();
  }
  if (typeof data === "string") {
    return textEncoder.encode(data);
  }
  if (data instanceof URLSearchParams) {
    return textEncoder.encode(data.toString());
  }
  return textEncoder.encode(JSON.stringify(data));
}

function isJsonBody(data: unknown): boolean {
  return data != null && typeof data === "object" && !isBinaryBody(data);
}

function isBinaryBody(data: unknown): boolean {
  return (
    (typeof FormData !== "undefined" && data instanceof FormData) ||
    (typeof Blob !== "undefined" && data instanceof Blob) ||
    data instanceof ArrayBuffer ||
    ArrayBuffer.isView(data) ||
    (typeof ReadableStream !== "undefined" && data instanceof ReadableStream)
  );
}

function contentTypeOf(config: GmAxiosConfig): string {
  return headerValue(config.headers, "Content-Type").split(";")[0].trim();
}

function headerValue(headers: GmAxiosConfig["headers"] | AxiosResponse["headers"], name: string): string {
  if (!headers) {
    return "";
  }
  if (typeof (headers as { get?: (header: string) => unknown }).get === "function") {
    return String((headers as { get: (header: string) => unknown }).get(name) || "");
  }
  const record = headers as Record<string, unknown>;
  return String(record[name] || record[name.toLowerCase()] || "");
}

function deleteHeader(headers: GmAxiosConfig["headers"] | AxiosResponse["headers"], name: string): void {
  if (headers && typeof (headers as { delete?: (header: string) => void }).delete === "function") {
    (headers as { delete: (header: string) => void }).delete(name);
    return;
  }
  if (!headers) {
    return;
  }
  const record = headers as Record<string, unknown>;
  delete record[name];
  delete record[name.toLowerCase()];
}

function setHeader(headers: GmAxiosConfig["headers"] | AxiosResponse["headers"], name: string, value: string): void {
  if (headers && typeof (headers as { set?: (header: string, headerValue: string) => void }).set === "function") {
    (headers as { set: (header: string, headerValue: string) => void }).set(name, value);
    return;
  }
  (headers as Record<string, string>)[name] = value;
}

function hasTransportHeader(headers: AxiosResponse["headers"]): boolean {
  return headerValue(headers, "X-Gm-Transport") === "1" || headerValue(headers, "x-gm-transport") === "1";
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) {
    binary += String.fromCharCode(value);
  }
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}
