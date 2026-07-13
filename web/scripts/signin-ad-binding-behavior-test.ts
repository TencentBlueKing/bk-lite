import assert from 'node:assert/strict';

import { getBindingPasswordCopy } from '../src/app/(core)/auth/signin/login-auth/bindingPasswordCopy';
import {
  isBindingPasswordSignin,
  isBindingSelectionLocked,
  resolveSigninSurface,
} from '../src/app/(core)/auth/signin/login-auth/orderedBindingState';

const builtinBinding = {
  id: 1,
  name: 'Platform Login',
  icon: 'user',
  description: 'Username and password',
  provider_key: 'bk_lite_builtin',
};

const adBinding = {
  id: 2,
  name: 'Corporate AD',
  icon: 'LDAP',
  description: 'Active Directory',
  provider_key: 'ad',
};

const feishuBinding = {
  id: 3,
  name: 'Feishu',
  icon: 'feishu',
  description: 'Feishu SSO',
  provider_key: 'feishu',
};

assert.equal(resolveSigninSurface('bindings-empty', null), 'builtin-password');
assert.equal(resolveSigninSurface('bindings-ready', builtinBinding), 'builtin-password');
assert.equal(resolveSigninSurface('bindings-ready', adBinding), 'binding-password');
assert.equal(resolveSigninSurface('bindings-ready', feishuBinding), 'binding-redirect');
assert.equal(isBindingPasswordSignin(adBinding), true);
assert.equal(isBindingPasswordSignin(feishuBinding), false);
assert.equal(
  isBindingSelectionLocked({ authStep: 'login', viewState: 'waiting' }),
  true,
);
assert.equal(
  isBindingSelectionLocked({ authStep: 'login', viewState: 'idle' }),
  false,
);

assert.deepEqual(getBindingPasswordCopy(adBinding), {
  usernameLabel: 'AD Username',
  usernamePlaceholder: 'Enter your AD username',
  passwordLabel: 'AD Password',
  passwordPlaceholder: 'Enter your AD password',
  submitText: 'Sign in with AD',
  loadingText: 'Signing in with AD...',
});

assert.deepEqual(getBindingPasswordCopy(feishuBinding), {
  usernameLabel: 'Feishu Username',
  usernamePlaceholder: 'Enter your Feishu username',
  passwordLabel: 'Feishu Password',
  passwordPlaceholder: 'Enter your Feishu password',
  submitText: 'Sign in with Feishu',
  loadingText: 'Signing in with Feishu...',
});

console.log('signin ad binding behavior tests passed');
