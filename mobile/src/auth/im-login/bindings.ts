import { detectImContainer } from './container';
import type { PublicLoginBinding } from './types';

const BUILTIN_PROVIDER_KEY = 'bk_lite_builtin';

/** OAuth that only works inside the matching IM in-app browser (not system Safari/Chrome). */
const CONTAINER_BOUND_OAUTH_PROVIDERS = new Set(['wecom']);

function evidenceModes(binding: PublicLoginBinding): string[] {
  return binding.client_login?.evidence_modes ?? [];
}

export function isBuiltinLoginBinding(binding?: PublicLoginBinding | null): boolean {
  return binding?.provider_key === BUILTIN_PROVIDER_KEY;
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

export function selectProviderOauthBinding(
  bindings: PublicLoginBinding[],
  providerKey: string,
): PublicLoginBinding | null {
  return selectOauthBindings(bindings).find((binding) => binding.provider_key === providerKey) ?? null;
}

/** Whether this binding can be offered on the current mobile client. */
export function isMobileBindingSupportedOnClient(
  binding: PublicLoginBinding,
  userAgent: string,
): boolean {
  if (isBuiltinLoginBinding(binding)) return true;
  if (!evidenceModes(binding).includes('oauth')) return false;
  if (!CONTAINER_BOUND_OAUTH_PROVIDERS.has(binding.provider_key)) return true;
  const container = detectImContainer(userAgent || '');
  return container?.providerKey === binding.provider_key;
}

/** Mobile methods: builtin password + oauth bindings supported on this client. */
export function selectMobileLoginBindings(
  bindings: PublicLoginBinding[],
  userAgent = '',
): PublicLoginBinding[] {
  return bindings.filter((binding) => isMobileBindingSupportedOnClient(binding, userAgent));
}

export function resolveInitialMobileBindingId(bindings: PublicLoginBinding[]): number | null {
  const builtin = bindings.find((binding) => isBuiltinLoginBinding(binding));
  return builtin?.id ?? bindings[0]?.id ?? null;
}

export function resolveSelectedMobileBinding(
  bindings: PublicLoginBinding[],
  selectedBindingId: number | null,
): PublicLoginBinding | null {
  return bindings.find((binding) => binding.id === selectedBindingId) ?? bindings[0] ?? null;
}
