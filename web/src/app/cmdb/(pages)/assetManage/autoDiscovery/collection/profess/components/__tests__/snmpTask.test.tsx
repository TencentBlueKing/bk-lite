import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import SNMPTask from '../snmpTask';

interface TaskOptions {
  initialValues: { credentialPool: CredentialPoolItem[] };
  formatValues: (values: Record<string, unknown>) => { credential: CredentialPoolItem[] };
}

let taskOptions: TaskOptions;

vi.mock('../../hooks/useTaskForm', () => ({
  getCleanupFormValues: () => ({}),
  useTaskForm: (options: TaskOptions) => {
    taskOptions = options;
    const [form] = Form.useForm();
    return { form, formatCycleValue: () => 300, onFinish: vi.fn() };
  },
}));
vi.mock('../baseTask', () => ({ default: () => null }));
vi.mock('../../hooks/useCollectionFormLayout', () => ({ useCollectionFormLayout: () => ({}) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/store/useAssetManage', () => ({
  default: () => ({ copyTaskData: null, setCopyTaskData: vi.fn() }),
}));

afterEach(cleanup);

function submitCredential(patch: CredentialPoolItem) {
  render(<SNMPTask
    onClose={() => undefined}
    selectedNode={{ id: 'network' } as React.ComponentProps<typeof SNMPTask>['selectedNode']}
    modelItem={{ model_id: 'network', task_type: 'snmp', type: 'protocol' } as React.ComponentProps<typeof SNMPTask>['modelItem']}
  />);
  // 使用任务自身的首组默认值与提交回调；JSON 序列化模拟真实请求中 undefined 字段被丢弃。
  return JSON.parse(JSON.stringify(taskOptions.formatValues({
    ...taskOptions.initialValues,
    credentialPool: [{ ...taskOptions.initialValues.credentialPool[0], ...patch }],
  }))).credential[0] as CredentialPoolItem;
}

it('首组凭据切换到 V3 authPriv 后提交界面默认的 SHA 和 AES', () => {
  const credential = submitCredential({
    version: 'v3', level: 'authPriv', username: 'test-user',
    authkey: 'test-auth-secret', privkey: 'test-privacy-secret',
  });
  expect(credential).toMatchObject({
    version: 'v3', level: 'authPriv', integrity: 'sha', privacy: 'aes',
    authkey: 'test-auth-secret', privkey: 'test-privacy-secret',
  });
});

it('未操作安全级别时提交界面默认的 authNoPriv，并排除加密字段', () => {
  const credential = submitCredential({
    version: 'v3', username: 'test-user', authkey: 'test-auth-secret',
  });
  expect(credential).toMatchObject({ level: 'authNoPriv', integrity: 'sha' });
  expect(credential).not.toHaveProperty('privacy');
  expect(credential).not.toHaveProperty('privkey');
});

it('保留用户选择的 MD5 和 DES', () => {
  const credential = submitCredential({
    version: 'v3', level: 'authPriv', username: 'test-user',
    integrity: 'md5', privacy: 'des',
    authkey: 'test-auth-secret', privkey: 'test-privacy-secret',
  });
  expect(credential).toMatchObject({ integrity: 'md5', privacy: 'des' });
});

it('编辑旧凭据缺少算法字段时补齐显示默认值，掩码密钥仍不提交', () => {
  const credential = submitCredential({
    credential_id: 'cred-existing', version: 'v3', level: 'authPriv',
    integrity: undefined, privacy: undefined, username: 'test-user',
    authkey: '******', privkey: '******',
  });
  expect(credential).toMatchObject({
    credential_id: 'cred-existing', integrity: 'sha', privacy: 'aes',
  });
  expect(credential).not.toHaveProperty('authkey');
  expect(credential).not.toHaveProperty('privkey');
});

it('空密钥保持缺失，交由凭据校验拒绝', () => {
  const credential = submitCredential({
    version: 'v3', level: 'authPriv', username: 'test-user', authkey: '', privkey: '',
  });
  expect(credential).not.toHaveProperty('authkey');
  expect(credential).not.toHaveProperty('privkey');
});

it.each(['v2', 'v2c'])('%s 提交仅保留团体字和端口', (version) => {
  expect(submitCredential({
    version, community: 'test-community', username: 'test-user', level: 'authPriv',
    integrity: 'sha', privacy: 'aes', authkey: 'test-auth-secret', privkey: 'test-privacy-secret',
  })).toEqual({ version, snmp_port: '161', community: 'test-community' });
});
