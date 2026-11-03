import { selectJsapiBinding } from './bindings';
import { detectImContainer } from './container';
import type {
  AuthCodeProof,
  ExternalLoginResult,
  PublicLoginBinding,
  SilentLoginOutcome,
} from './types';
import type { ExternalSessionStatus } from './session';

interface SilentLoginDependencies {
  userAgent: string;
  loadBindings: () => Promise<PublicLoginBinding[]>;
  getAuthCode: (binding: PublicLoginBinding) => Promise<AuthCodeProof>;
  exchange: (binding: PublicLoginBinding, proof: AuthCodeProof) => Promise<ExternalLoginResult | null>;
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

  const binding = selectJsapiBinding(bindings, container);
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
  return { status: 'degraded', notice: { reason: 'session_failed', name: binding.name } };
}
