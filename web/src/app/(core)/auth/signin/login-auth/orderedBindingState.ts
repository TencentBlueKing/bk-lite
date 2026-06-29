import type {
  LoginAuthBindingItem,
  LoginAuthBindingsLoadState,
  LoginAuthValidationViewState,
} from './types';

const BUILTIN_PROVIDER_KEY = 'bk_lite_builtin';

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

export function shouldUseBuiltinSigninForm(
  bindingsLoadState: LoginAuthBindingsLoadState,
  selectedBinding?: LoginAuthBindingItem | null,
): boolean {
  return (
    bindingsLoadState === 'bindings-error'
    || bindingsLoadState === 'bindings-empty'
    || (bindingsLoadState === 'bindings-ready' && isBuiltinBinding(selectedBinding))
  );
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
