import assert from 'node:assert/strict';

import { Form } from 'antd';
import React from 'react';
import type { ReactElement, ReactNode } from 'react';

import type { IntegrationInstance, ProviderManifest, TemplateField } from '../src/app/system-manager/types/integration-center';

const frontendUrl = new URL('https://bklite.canway.net:443/system-manager/integration-center/detail?id=42');
const expectedCallbackUrl = 'https://bklite.canway.net/api/v1/core/api/login_auth/callback/';
const backendInternalCallbackUrl = 'http://10.0.0.12:8000/api/v1/core/api/login_auth/callback/';

Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: {
    location: frontendUrl,
    addEventListener(eventName: string, listener: EventListener) {
      void eventName;
      void listener;
    },
    removeEventListener(eventName: string, listener: EventListener) {
      void eventName;
      void listener;
    },
  },
});

const templateField: TemplateField = {
  key: 'client_id',
  label: 'Client ID',
  field_type: 'string',
  required: true,
  secret: false,
  write_only: false,
  mask_strategy: 'full',
  default: '',
  placeholder: '',
  help_text: '',
  options: [],
  reset_capabilities: [],
};

const backendInstance: IntegrationInstance = {
  id: 42,
  name: 'OIDC SSO',
  provider_key: 'oidc',
  provider: { key: 'oidc', name: 'OIDC' },
  description: 'login auth detail fixture',
  enabled: true,
  status: 'ready',
  capability_status: { login_auth: 'ready' },
  capability_enabled: { login_auth: true },
  team: [],
  config: { client_id: 'client-from-backend' },
  login_auth_callback_url: backendInternalCallbackUrl,
  created_at: '2026-07-06T00:00:00Z',
  updated_at: '2026-07-06T00:00:00Z',
};

const providerManifest: ProviderManifest = {
  key: 'oidc',
  name: 'OIDC',
  description: 'OIDC provider',
  instance_template: [],
  instance_templates: {},
  business_templates: {},
  capabilities: [
    {
      key: 'login_auth',
      name: 'Login Auth',
      description: 'Login authentication',
      connection_template: [templateField],
      business_template: '',
    },
  ],
};

const reactForHarness = React as typeof React & {
  useMemo: <T>(factory: () => T, deps?: unknown[]) => T;
  useEffect: (effect: () => unknown, deps?: unknown[]) => void;
  useCallback: <T extends (...args: never[]) => unknown>(callback: T, deps?: unknown[]) => T;
  useContext: (context: { displayName?: string } | null) => unknown;
  useRef: <T>(initialValue: T) => { current: T };
  useState: <T>(initialState: T | (() => T)) => [T, (nextState: T | ((previousState: T) => T)) => void];
};

let stateCallIndex = 0;
const renderedState = [
  true,
  backendInstance,
  [providerManifest],
  false,
  false,
  false,
  false,
  'login_auth',
];
const ignoredStateUpdates: unknown[] = [];

reactForHarness.useState = <T,>(initialState: T | (() => T)) => {
  const fixtureValue = stateCallIndex < renderedState.length
    ? renderedState[stateCallIndex]
    : initialState;
  stateCallIndex += 1;
  const resolvedValue = typeof fixtureValue === 'function'
    ? (fixtureValue as () => T)()
    : fixtureValue;
  const setter = (nextState: T | ((previousState: T) => T)) => {
    ignoredStateUpdates.push(nextState);
  };
  return [resolvedValue as T, setter];
};

reactForHarness.useMemo = (factory) => {
  return factory();
};

reactForHarness.useEffect = (effect) => {
  void effect;
};

reactForHarness.useCallback = (callback) => {
  return callback;
};

reactForHarness.useRef = (initialValue) => {
  return { current: initialValue };
};

reactForHarness.useContext = (context) => {
  if (context?.displayName === 'SearchParamsContext') {
    return frontendUrl.searchParams;
  }

  if (context?.displayName === 'NavigationPromisesContext') {
    return null;
  }

  if (context?.displayName === 'AppRouterContext') {
    return {
      push(path: string) {
        ignoredStateUpdates.push(['router.push', path]);
      },
      replace(path: string) {
        ignoredStateUpdates.push(['router.replace', path]);
      },
    };
  }

  return {
    token: 'test-token',
    data: { user: { token: 'test-token' } },
    status: 'authenticated',
    update(nextSession: unknown) {
      ignoredStateUpdates.push(nextSession);
    },
    formatMessage(message: { id?: string; defaultMessage?: string }) {
      return message.defaultMessage || message.id || '';
    },
  };
};

Object.defineProperty(Form, 'useForm', {
  configurable: true,
  value() {
    return [{
      setFieldsValue(values: unknown) {
        ignoredStateUpdates.push(values);
      },
      async validateFields() {
        return { config: {} };
      },
    }];
  },
});

function collectRenderedCallbackValues(node: ReactNode, values: string[]) {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return;
  }

  if (Array.isArray(node)) {
    for (const child of node) {
      collectRenderedCallbackValues(child, values);
    }
    return;
  }

  if (typeof node !== 'object') {
    return;
  }

  const props = (node as ReactElement<{ children?: ReactNode; suffix?: ReactNode; value?: unknown }>).props;
  if (typeof props?.value === 'string' && props.value.includes('/api/v1/core/api/login_auth/callback/')) {
    values.push(props.value);
  }

  collectRenderedCallbackValues(props?.children, values);
  collectRenderedCallbackValues(props?.suffix, values);
}

async function runContract() {
  // This test patches React hooks before loading the client page; a static import would
  // bind the page to real Next/React hooks before the harness can inject fixture state.
  const { default: IntegrationDetailPage } = await import('../src/app/system-manager/(pages)/integration-center/detail/page');

  const renderedTree = IntegrationDetailPage({});
  const callbackValues: string[] = [];
  collectRenderedCallbackValues(renderedTree, callbackValues);

  assert.deepEqual(
    callbackValues,
    [expectedCallbackUrl],
    [
      '登录认证详情页展示的回调地址必须由当前前端 origin 拼出。',
      `当前 origin: ${frontendUrl.origin}`,
      `后端返回的内网回调地址: ${backendInternalCallbackUrl}`,
      `实际渲染值: ${callbackValues.length > 0 ? callbackValues.join(', ') : '<未渲染回调地址>'}`,
    ].join('\n')
  );

  assert.equal(
    callbackValues.includes(backendInternalCallbackUrl),
    false,
    '详情页不能直接展示后端 login_auth_callback_url 中的内网 IP'
  );

  console.log('integration center login auth callback origin test passed');
}

runContract().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
