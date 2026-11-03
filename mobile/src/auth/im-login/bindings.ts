import type { PublicLoginBinding } from './types';

function evidenceModes(binding: PublicLoginBinding): string[] {
  return binding.client_login?.evidence_modes ?? [];
}

export function selectJsapiBinding(
  bindings: PublicLoginBinding[],
  providerKey: string,
): PublicLoginBinding | null {
  return bindings.find((binding) => {
    const appId = binding.client_login?.jsapi?.app_id?.trim();
    return binding.provider_key === providerKey
      && evidenceModes(binding).includes('jsapi')
      && Boolean(appId);
  }) ?? null;
}

export function selectOauthBindings(bindings: PublicLoginBinding[]): PublicLoginBinding[] {
  return bindings.filter((binding) => evidenceModes(binding).includes('oauth'));
}
