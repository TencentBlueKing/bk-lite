import assert from 'node:assert/strict';

import {
  isBindingSelectionLocked,
  isBuiltinBinding,
  resolveInlineValidationError,
  resolveBindingsLoadState,
  resolveInitialBindingId,
  resolveSelectedBinding,
  shouldUseBuiltinSigninForm,
} from '../src/app/(core)/auth/signin/login-auth/orderedBindingState';

const bindings = [
  { id: 11, name: 'Feishu', icon: 'feishu', description: 'Feishu SSO', provider_key: 'feishu' },
  { id: 12, name: 'Platform Login', icon: 'user', description: 'Username and password', provider_key: 'bk_lite_builtin' },
];

assert.equal(resolveInitialBindingId(bindings), 11);
assert.equal(resolveSelectedBinding(bindings, null)?.id, 11);
assert.equal(resolveSelectedBinding(bindings, 12)?.provider_key, 'bk_lite_builtin');
assert.equal(resolveSelectedBinding(bindings, 999)?.id, 11);
assert.equal(resolveBindingsLoadState(bindings, false), 'bindings-ready');
assert.equal(resolveBindingsLoadState([], false), 'bindings-empty');
assert.equal(resolveBindingsLoadState([], true), 'bindings-error');
assert.equal(shouldUseBuiltinSigninForm('bindings-error', null), true);
assert.equal(shouldUseBuiltinSigninForm('bindings-empty', null), true);
assert.equal(shouldUseBuiltinSigninForm('bindings-ready', bindings[1]), true);
assert.equal(shouldUseBuiltinSigninForm('bindings-ready', bindings[0]), false);
assert.equal(
  resolveInlineValidationError('bindings-error', 'idle', 'Failed to load login methods. Please refresh and try again.'),
  'Failed to load login methods. Please refresh and try again.',
);
assert.equal(
  resolveInlineValidationError('bindings-ready', 'failed', 'Authentication failed. Please try again.'),
  'Authentication failed. Please try again.',
);
assert.equal(resolveInlineValidationError('bindings-ready', 'idle', 'ignored'), '');
assert.equal(isBuiltinBinding(bindings[1]), true);
assert.equal(
  isBindingSelectionLocked({ authStep: 'otp-verification', viewState: 'idle' }),
  true,
);
assert.equal(
  isBindingSelectionLocked({ authStep: 'login', viewState: 'waiting' }),
  true,
);
assert.equal(
  isBindingSelectionLocked({ authStep: 'login', viewState: 'idle' }),
  false,
);

console.log('signin binding ordered rendering tests passed');
