import type { AuthCodeProof, PublicLoginBinding } from '../types';
import { requestFeishuAuthCode, type FeishuHost } from './feishu';

export interface ImAuthCodeProvider {
  getAuthCode: (binding: PublicLoginBinding, host: FeishuHost) => Promise<AuthCodeProof>;
}

const providers: Record<string, ImAuthCodeProvider> = {
  feishu: {
    getAuthCode: (binding, host) => requestFeishuAuthCode(binding.client_login?.jsapi?.app_id || '', host),
  },
};

export function getImAuthCodeProvider(providerKey: string): ImAuthCodeProvider | null {
  return providers[providerKey] ?? null;
}
