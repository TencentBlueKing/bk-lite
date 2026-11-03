import { apiGet, apiPost } from '@/api/request';
import { isTauriApp } from '@/utils/tauriFetch';
import { withBasePath } from '@/utils/basePath';
import { selectOauthBindings } from './bindings';
import { saveOAuthPending, clearOAuthPending, completeOAuthReturn, readOAuthPending, readOAuthReturnStatus } from './oauth';
import { getImAuthCodeProvider } from './providers';
import { loadFeishuH5Sdk, type FeishuHost } from './providers/feishu';
import { establishH5SessionFromLoginResult } from './session';
import { runSilentImLogin } from './shell';
import type { AuthCodeProof, ExternalLoginResult, PublicLoginBinding } from './types';

interface SessionDependencies {
  signIn: (provider: string, options: Record<string, unknown>) => Promise<{ ok?: boolean } | undefined>;
  getSession: () => Promise<unknown>;
  signOut: (options: { redirect: false }) => Promise<unknown>;
}

interface LoginBindingsResponse {
  result?: boolean;
  data?: PublicLoginBinding[];
}

interface LoginExchangeResponse {
  result?: boolean;
  data?: ExternalLoginResult;
}

interface StartLoginResponse {
  result?: boolean;
  data?: {
    auth_request_id?: string;
    poll_token?: string;
    login_url?: string;
  };
}

interface StatusResponse {
  result?: boolean;
  data?: {
    status?: string;
    login_result?: ExternalLoginResult;
  };
}

async function loadPublicBindings(): Promise<PublicLoginBinding[]> {
  const response = await apiGet<LoginBindingsResponse>('/core/api/get_login_auth_bindings');
  if (!response?.result || !Array.isArray(response.data)) return [];
  return response.data;
}

async function acquireAuthCode(binding: PublicLoginBinding): Promise<AuthCodeProof> {
  const provider = getImAuthCodeProvider(binding.provider_key);
  if (!provider) throw new Error('missing_provider');
  const host = window as unknown as FeishuHost;
  if (binding.provider_key === 'feishu' && !host.tt) {
    await loadFeishuH5Sdk(document);
  }
  return provider.getAuthCode(binding, window as unknown as FeishuHost);
}

async function exchangeAuthCode(
  binding: PublicLoginBinding,
  proof: AuthCodeProof,
): Promise<ExternalLoginResult | null> {
  const response = await apiPost<LoginExchangeResponse>('/core/api/login/', {
    binding_id: binding.id,
    auth_code: proof.code,
    evidence_mode: proof.evidenceMode,
    ...(proof.jsapiCodeType ? { jsapi_code_type: proof.jsapiCodeType } : {}),
  });
  if (!response?.result || !response.data) return null;
  return response.data;
}

export async function loadOauthLoginBindings(): Promise<PublicLoginBinding[]> {
  if (isTauriApp()) return [];
  return selectOauthBindings(await loadPublicBindings());
}

export async function startBrowserExternalLogin(binding: PublicLoginBinding): Promise<boolean> {
  const response = await apiPost<StartLoginResponse>('/core/api/start_login_auth/', {
    binding_id: binding.id,
    callback_url: withBasePath('/'),
    redirect_origin: window.location.origin,
    result_path: withBasePath('/auth/external'),
  });
  const data = response?.data;
  if (!response?.result || !data?.login_url || !data.auth_request_id || !data.poll_token) {
    return false;
  }
  saveOAuthPending(window.sessionStorage, {
    authRequestId: data.auth_request_id,
    pollToken: data.poll_token,
    bindingName: binding.name,
  });
  window.location.assign(data.login_url);
  return true;
}

export function runBrowserSilentLogin(dependencies: SessionDependencies) {
  return runSilentImLogin({
    userAgent: window.navigator.userAgent,
    loadBindings: loadPublicBindings,
    getAuthCode: acquireAuthCode,
    exchange: exchangeAuthCode,
    establishSession: (loginResult) => establishH5SessionFromLoginResult(loginResult, dependencies),
  });
}

export function completeBrowserExternalLogin(dependencies: SessionDependencies) {
  const pending = readOAuthPending(window.sessionStorage);
  clearOAuthPending(window.sessionStorage);
  return completeOAuthReturn({
    pending,
    returnStatus: readOAuthReturnStatus(window.location.search),
    fetchStatus: async (item) => {
      const response = await apiGet<StatusResponse>(
        `/core/api/login_auth_requests/${encodeURIComponent(item.authRequestId)}/status`,
        { poll_token: item.pollToken },
      );
      if (!response?.result || !response.data) return null;
      return response.data;
    },
    establishSession: (loginResult) => establishH5SessionFromLoginResult(loginResult, dependencies),
  });
}
