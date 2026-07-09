import type {
  LoginAuthBindingItem,
  LoginAuthBindingsLoadState,
  LoginAuthValidationViewState,
  SigninSurface,
} from './types';

const BUILTIN_PROVIDER_KEY = 'bk_lite_builtin';
const BINDING_PASSWORD_PROVIDER_KEYS = new Set(['ad']);

export function resolveInitialBindingId(bindings: LoginAuthBindingItem[]): number | null {
  return bindings[0]?.id ?? null;
}

export function resolveSelectedBinding(
  bindings: LoginAuthBindingItem[],
  selectedBindingId: number | null,
): LoginAuthBindingItem | null {
  return bindings.find((binding) => binding.id === selectedBindingId) ?? bindings[0] ?? null;
}

export function resolveBindingsLoadState(
  bindings: LoginAuthBindingItem[],
  requestFailed: boolean,
): LoginAuthBindingsLoadState {
  if (requestFailed) {
    return 'bindings-error';
  }

  return bindings.length > 0 ? 'bindings-ready' : 'bindings-empty';
}

export function isBuiltinBinding(binding?: LoginAuthBindingItem | null): boolean {
  return binding?.provider_key === BUILTIN_PROVIDER_KEY;
}

export function isBindingPasswordSignin(binding?: LoginAuthBindingItem | null): boolean {
  return Boolean(binding?.provider_key && BINDING_PASSWORD_PROVIDER_KEYS.has(binding.provider_key));
}

export function resolveSigninSurface(
  bindingsLoadState: LoginAuthBindingsLoadState,
  selectedBinding?: LoginAuthBindingItem | null,
): SigninSurface {
  if (
    bindingsLoadState === 'bindings-error'
    || bindingsLoadState === 'bindings-empty'
    || (bindingsLoadState === 'bindings-ready' && isBuiltinBinding(selectedBinding))
  ) {
    return 'builtin-password';
  }

  if (bindingsLoadState === 'bindings-ready' && isBindingPasswordSignin(selectedBinding)) {
    return 'binding-password';
  }

  return 'binding-redirect';
}

export function shouldUseBuiltinSigninForm(
  bindingsLoadState: LoginAuthBindingsLoadState,
  selectedBinding?: LoginAuthBindingItem | null,
): boolean {
  return resolveSigninSurface(bindingsLoadState, selectedBinding) === 'builtin-password';
}

export function resolveInlineValidationError(
  bindingsLoadState: LoginAuthBindingsLoadState,
  viewState: LoginAuthValidationViewState,
  errorMessage: string,
): string {
  if (bindingsLoadState === 'bindings-error') {
    return errorMessage;
  }

  return ['failed', 'cancelled', 'expired'].includes(viewState) ? errorMessage : '';
}

export function isBindingSelectionLocked(args: {
  authStep: 'login' | 'reset-password' | 'otp-verification';
  viewState: LoginAuthValidationViewState;
}): boolean {
  return (
    args.authStep !== 'login'
    || args.viewState === 'starting'
    || args.viewState === 'waiting'
    || args.viewState === 'syncing-session'
  );
}

export function shouldShowBindingsSelector(args: {
  authStep: 'login' | 'reset-password' | 'otp-verification';
  bindingsLoadState: LoginAuthBindingsLoadState;
  bindingsCount: number;
}): boolean {
  return (
    args.authStep === 'login'
    && args.bindingsLoadState === 'bindings-ready'
    && args.bindingsCount > 1
  );
}
