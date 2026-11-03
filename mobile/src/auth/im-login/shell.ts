import { selectJsapiBinding, selectProviderOauthBinding } from './bindings';
import { detectImContainer } from './container';
import type {
  AuthCodeProof,
  ExternalLoginResult,
  PublicLoginBinding,
  SilentLoginOutcome,
} from './types';
import { noticeForExternalSession, type ExternalSessionStatus } from './session';

interface SilentLoginDependencies {
  userAgent: string;
  loadBindings: () => Promise<PublicLoginBinding[]>;
  getAuthCode: (binding: PublicLoginBinding) => Promise<AuthCodeProof>;
  exchange: (binding: PublicLoginBinding, proof: AuthCodeProof) => Promise<ExternalLoginResult | null>;
  startOauth?: (binding: PublicLoginBinding) => Promise<boolean>;
  establishSession: (loginResult: ExternalLoginResult) => Promise<ExternalSessionStatus>;
}

export async function runSilentImLogin(
  dependencies: SilentLoginDependencies,
): Promise<SilentLoginOutcome> {
  const container = detectImContainer(dependencies.userAgent);
  if (!container) return { status: 'skipped' };

  let bindings: PublicLoginBinding[] = [];
  try {
    bindings = await dependencies.loadBindings();
  } catch {
    return { status: 'degraded', notice: { reason: 'exchange_failed', name: '' } };
  }

  if (container.silent === 'oauth') {
    return runOauthSilentLogin(container.providerKey, bindings, dependencies);
  }

  const binding = selectJsapiBinding(bindings, container.providerKey);
  if (!binding) return { status: 'skipped' };

  let proof: AuthCodeProof;
  try {
    proof = await dependencies.getAuthCode(binding);
  } catch {
    return { status: 'degraded', notice: { reason: 'jsapi_failed', name: binding.name } };
  }

  let loginResult: ExternalLoginResult | null;
  try {
    loginResult = await dependencies.exchange(binding, proof);
  } catch {
    return { status: 'degraded', notice: { reason: 'exchange_failed', name: binding.name } };
  }
  if (!loginResult) {
    return { status: 'degraded', notice: { reason: 'exchange_failed', name: binding.name } };
  }

  const session = await dependencies.establishSession(loginResult);
  if (session.status === 'success') {
    return { status: 'success', token: session.token };
  }
  return { status: 'degraded', notice: noticeForExternalSession(session.status, binding.name) };
}

async function runOauthSilentLogin(
  providerKey: string,
  bindings: PublicLoginBinding[],
  dependencies: SilentLoginDependencies,
): Promise<SilentLoginOutcome> {
  const binding = selectProviderOauthBinding(bindings, providerKey);
  if (!binding) return { status: 'skipped' };
  if (!dependencies.startOauth) {
    return { status: 'degraded', notice: { reason: 'oauth_failed', name: binding.name } };
  }

  try {
    const started = await dependencies.startOauth(binding);
    if (!started) {
      return { status: 'degraded', notice: { reason: 'oauth_failed', name: binding.name } };
    }
  } catch {
    return { status: 'degraded', notice: { reason: 'oauth_failed', name: binding.name } };
  }
  return { status: 'redirecting' };
}
