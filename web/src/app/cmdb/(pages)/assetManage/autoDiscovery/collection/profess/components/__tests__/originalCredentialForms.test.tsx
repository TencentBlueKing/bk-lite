import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import CredentialPoolEditor, { type CredentialPoolEditorProps } from '../credentialPoolEditor';
import { getCredentialDescriptor } from '../credentialDescriptors';
import type { CredentialPoolItem, ModelItem } from '@/app/cmdb/types/autoDiscovery';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }),
}));
vi.mock('@/components/credential-picker', () => ({ default: () => <div>凭据选择</div> }));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: () => false,
  }) });
});
afterEach(cleanup);

interface Entry extends Partial<ModelItem> {
  id: string;
  original_form: string;
  effective_form?: string;
  binding: string | null;
}
const entries: Entry[] = JSON.parse(readFileSync(
  resolve(process.cwd(), '../server/apps/cmdb/tests/fixtures/collection_original_forms.json'), 'utf8',
));

it.each(entries)('$id 一次性认证渲染并更新原始认证字段', (entry) => {
  const descriptor = getCredentialDescriptor(entry);
  if (entry.original_form === 'none') {
    expect(descriptor).toBeNull();
    return;
  }
  const form = entry.id === 'pc' ? 'winrm' : entry.id === 'config_file' ? 'config_file' : descriptor?.formKind;
  expect(form).toBe(entry.effective_form || entry.original_form);
  const shape = (form === 'vmware' ? 'vm' : form) as CredentialPoolEditorProps['credentialShape'];
  const keys = shape === 'cloud' ? ['accessKey', 'accessSecret']
    : shape === 'snmp' ? ['community']
    : shape === 'influxdb' ? ['token']
    : [shape === 'sql' || shape === 'winsphere' ? 'user' : 'username', 'password'];
  const credential: CredentialPoolItem = {
    credential_source: 'inline', port: 12345, snmp_port: 12345, https_port: 12345,
    version: 'v2', scheme: 'https', verify_tls: true, certValidation: true,
    ...Object.fromEntries(keys.map((key) => [key, `original-${key}`])),
  };
  const onChange = vi.fn();
  const editor = <CredentialPoolEditor
    credentialShape={shape} value={[credential]} onChange={onChange}
    vaultCategory={entry.binding?.split('/')[0]} vaultTypeKeys={entry.binding ? [entry.binding.split('/')[1]] : []}
    credentialSchema={shape === 'winsphere' ? {
      schema_version: 1, allow_multiple: false, allow_unknown_fields: false, encrypted_fields: ['password'], fields: [
        { key: 'user', type: 'string', label: '账号', required: true },
        { key: 'password', type: 'password', label: '密码', required: true },
        { key: 'https_port', type: 'integer', label: '端口', required: true },
        { key: 'verify_tls', type: 'boolean', label: '证书校验', required: true },
      ],
    } : undefined}
  />;
  const { container, getByRole, queryByText, rerender } = render(editor);
  expect(getByRole('button', { name: '使用已有凭据' })).toBeTruthy();
  expect(queryByText('凭据选择')).toBeNull();
  for (const key of keys) {
    const input = Array.from(container.querySelectorAll('input')).find((item) => item.value === `original-${key}`);
    expect(input, `${entry.id}: ${key}`).toBeTruthy();
    fireEvent.change(input!, { target: { value: `changed-${key}` } });
    expect(onChange.mock.lastCall?.[0][0][key]).toBe(`changed-${key}`);
    expect(onChange.mock.lastCall?.[0][0].credential_source).toBe('inline');
  }
  if (entry.binding) {
    fireEvent.click(getByRole('button', { name: '使用已有凭据' }));
    const vault = onChange.mock.lastCall?.[0];
    expect(vault[0]).toMatchObject({ credential_source: 'vault', vault_type_key: entry.binding.split('/')[1], port: 12345 });
    for (const key of keys) expect(vault[0][key]).toBeUndefined();
    rerender(React.cloneElement(editor, { value: vault }));
    expect(queryByText('凭据选择')).toBeTruthy();
    fireEvent.click(getByRole('button', { name: '改用手动录入' }));
    const inline = onChange.mock.lastCall?.[0];
    expect(inline[0]).toMatchObject({ credential_source: 'inline', port: 12345 });
    expect(inline[0].vault_type_key).toBeUndefined();
    rerender(React.cloneElement(editor, { value: inline }));
    expect(getByRole('button', { name: '使用已有凭据' })).toBeTruthy();
    expect(queryByText('凭据选择')).toBeNull();
  }
});
