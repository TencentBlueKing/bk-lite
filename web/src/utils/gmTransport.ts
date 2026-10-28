import { AxiosResponse, InternalAxiosRequestConfig } from "axios";

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

interface GmApi {
  resetGmTransportCache: () => void;
  invalidateGmTransportCache: () => void;
  loadGmPublic: (force?: boolean) => Promise<GmPublic>;
  prepareGmAxiosRequest: (config: GmAxiosConfig) => Promise<GmAxiosConfig>;
  discardGmAxiosKey: (config?: GmAxiosConfig | null) => void;
  openGmAxiosResponse: (response: AxiosResponse) => Promise<AxiosResponse>;
  retryGmAxiosRequest: (error: {
    config?: GmAxiosConfig;
    response?: { status?: number; data?: { code?: string } };
  }) => Promise<boolean>;
  gmFetch: (input: RequestInfo | URL, init?: RequestInit, retried?: boolean) => Promise<Response>;
}

const plaintext: GmApi = {
  resetGmTransportCache() {},
  invalidateGmTransportCache() {},
  async loadGmPublic() {
    return { enabled: "0" };
  },
  async prepareGmAxiosRequest(config) {
    return config;
  },
  discardGmAxiosKey() {},
  async openGmAxiosResponse(response) {
    return response;
  },
  async retryGmAxiosRequest() {
    return false;
  },
  gmFetch(input, init) {
    return fetch(input, init);
  },
};

function readEnterpriseGmTransport(): GmApi | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("@/app/system-manager/(enterprise)/utils/gmTransport") as GmApi;
  } catch {
    return null;
  }
}

export function selectGmTransport(module: GmApi | null): GmApi & { available: boolean } {
  const api = module?.gmFetch ? module : plaintext;
  return {
    available: api !== plaintext,
    resetGmTransportCache: api.resetGmTransportCache,
    invalidateGmTransportCache: api.invalidateGmTransportCache,
    loadGmPublic: api.loadGmPublic,
    prepareGmAxiosRequest: api.prepareGmAxiosRequest,
    discardGmAxiosKey: api.discardGmAxiosKey,
    openGmAxiosResponse: api.openGmAxiosResponse,
    retryGmAxiosRequest: api.retryGmAxiosRequest,
    gmFetch: api.gmFetch,
  };
}

const selected = selectGmTransport(readEnterpriseGmTransport());

export const gmTransportAvailable = selected.available;
export const resetGmTransportCache = selected.resetGmTransportCache;
export const invalidateGmTransportCache = selected.invalidateGmTransportCache;
export const loadGmPublic = selected.loadGmPublic;
export const prepareGmAxiosRequest = selected.prepareGmAxiosRequest;
export const discardGmAxiosKey = selected.discardGmAxiosKey;
export const openGmAxiosResponse = selected.openGmAxiosResponse;
export const retryGmAxiosRequest = selected.retryGmAxiosRequest;
export const gmFetch = selected.gmFetch;
