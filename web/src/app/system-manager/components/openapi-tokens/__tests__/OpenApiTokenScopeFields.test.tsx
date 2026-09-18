import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Form } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import OpenApiTokenScopeFields from '../OpenApiTokenScopeFields';
import type { OpenApiTokenServiceCatalog } from '../types';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

beforeAll(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

const catalog: OpenApiTokenServiceCatalog[] = [
  {
    name: 'cmdb',
    kind: 'internal',
    label: 'cmdb',
    endpoints: [
      { key: 'GET cmdb/classifications', label: '模型分类', method: 'GET', path: 'cmdb/classifications' },
      { key: 'GET cmdb/instances', label: '实例列表', method: 'GET', path: 'cmdb/instances' },
    ],
  },
  {
    name: 'itsm',
    kind: 'external',
    label: 'itsm',
    endpoints: [{ key: 'EXTERNAL itsm', label: 'itsm' }],
  },
];

const renderScope = () => render(
  <Form initialValues={{ scopeMode: 'allowlist', scopeEndpoints: [] }}>
    <OpenApiTokenScopeFields catalog={catalog} />
  </Form>,
);

afterEach(() => {
  cleanup();
});

describe('OpenApiTokenScopeFields', () => {
  it('replaces the previous service endpoints when switching tabs', () => {
    renderScope();
    expect(screen.getByText('GET cmdb/classifications')).toBeTruthy();
    expect(screen.queryByText('EXTERNAL itsm')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: 'itsm' }));

    expect(screen.queryByText('GET cmdb/classifications')).toBeNull();
    expect(screen.getByText('EXTERNAL itsm')).toBeTruthy();
  });

  it('shows the first service after catalog arrives on an already mounted picker', () => {
    const { rerender } = render(
      <Form initialValues={{ scopeMode: 'allowlist', scopeEndpoints: [] }}>
        <OpenApiTokenScopeFields catalog={[]} />
      </Form>,
    );
    expect(screen.getByText('system.settings.secret.scopeEmptyCatalog')).toBeTruthy();

    rerender(
      <Form initialValues={{ scopeMode: 'allowlist', scopeEndpoints: [] }}>
        <OpenApiTokenScopeFields catalog={catalog} />
      </Form>,
    );

    expect(screen.getByText('GET cmdb/classifications')).toBeTruthy();
    expect(screen.queryByText('system.settings.secret.scopeEmptyCatalog')).toBeNull();
  });

  it('does not light up select-all when only some endpoints are checked', () => {
    render(
      <Form initialValues={{
        scopeMode: 'allowlist',
        scopeEndpoints: ['GET cmdb/classifications'],
      }}
      >
        <OpenApiTokenScopeFields catalog={catalog} />
      </Form>,
    );

    const selectAll = screen.getByRole('checkbox', { name: 'system.settings.secret.scopeSelectAll' }) as HTMLInputElement;
    expect(selectAll.checked).toBe(false);
    expect(selectAll.getAttribute('aria-checked')).not.toBe('mixed');
    expect(screen.getByRole('checkbox', { name: /GET cmdb\/classifications/i })).toHaveProperty('checked', true);
    expect(screen.getByRole('checkbox', { name: /GET cmdb\/instances/i })).toHaveProperty('checked', false);
  });

  it('lights up select-all only when every endpoint in the service is checked', () => {
    render(
      <Form initialValues={{
        scopeMode: 'allowlist',
        scopeEndpoints: ['GET cmdb/classifications', 'GET cmdb/instances'],
      }}
      >
        <OpenApiTokenScopeFields catalog={catalog} />
      </Form>,
    );

    expect(
      (screen.getByRole('checkbox', { name: 'system.settings.secret.scopeSelectAll' }) as HTMLInputElement).checked,
    ).toBe(true);
  });
});
