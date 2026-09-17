import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import HostTask from '../hostTask';
import { resolveCredentialHelp } from '../credentialHelp';
import zh from '@/app/cmdb/locales/zh.json';

vi.mock('../../hooks/useTaskForm', () => ({
  useTaskForm: () => ({ form: { setFieldsValue: vi.fn() }, loading: false, submitLoading: false }),
}));
vi.mock('../baseTask', () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('../credentialPoolEditor', () => ({ default: () => <div>credential pool</div> }));
vi.mock('../../hooks/useCollectionFormLayout', () => ({ useCollectionFormLayout: () => ({}) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/store/useAssetManage', () => ({ default: () => ({ copyTaskData: null, setCopyTaskData: vi.fn() }) }));
vi.mock('antd', () => ({
  Spin: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Form: Object.assign(({ children }: { children: React.ReactNode }) => <div>{children}</div>, { Item: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }),
  Alert: ({ message }: { message: string }) => <div role="alert">{message}</div>,
}));
afterEach(cleanup);

it.each(['cisco_fc', 'brocade_fc'])('%s 不显示留空走 Agent 的提示', (modelId) => {
  renderTask(modelId, 'job');
  expect(screen.getByRole('alert').textContent).toBe('Collection.deviceJobCredentialTip');
  expect(resolveCredentialHelp({ model_id: modelId, type: 'job', credential_protocol: 'ssh' }, (key) => key).instruction)
    .toBe('Collection.credentialHelp.instruction.deviceSsh');
});
it('主机 JOB 展示有前提的 Agent 提示', () => {
  renderTask('host', 'job');
  expect(screen.getByRole('alert').textContent).toBe('Collection.hostCredentialOptionalTip');
  expect(zh.Collection.hostCredentialOptionalTip).toContain('已接入可用 Agent');
  expect(zh.Collection.hostCredentialOptionalTip).not.toContain('留空时将走');
});
it('协议插件即使复用表单也不能出现 Agent 提示', () => {
  renderTask('example', 'protocol');
  expect(screen.queryByRole('alert')).toBeNull();
});
function renderTask(modelId: string, type: string) {
  render(<HostTask onClose={() => undefined}
    selectedNode={{ id: 'test' } as React.ComponentProps<typeof HostTask>['selectedNode']}
    modelItem={{ model_id: modelId, type } as React.ComponentProps<typeof HostTask>['modelItem']} />);
}
