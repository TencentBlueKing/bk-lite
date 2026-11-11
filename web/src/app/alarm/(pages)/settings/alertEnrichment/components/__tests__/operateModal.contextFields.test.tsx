import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OperateModal from '../operateModal';
import type { EnrichmentRuleListItem } from '@/app/alarm/types/settings';

const api = vi.hoisted(() => ({
  createEnrichment: vi.fn(),
  updateEnrichment: vi.fn(),
  getCmdbContextFields: vi.fn(),
}));

vi.mock('@/app/alarm/api/settings', () => ({ useSettingApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/(pages)/settings/components/matchRule', () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  api.getCmdbContextFields.mockResolvedValue({
    groups: [
      {
        model_id: 'application',
        model_name: '应用',
        fields: [{ source: 'application.inst_name', attr_name: '应用名称' }],
      },
      {
        model_id: 'system',
        model_name: '应用系统',
        fields: [{ source: 'system.operator', attr_name: '运维人员' }],
      },
    ],
  });
});

afterEach(cleanup);

const baseRow: EnrichmentRuleListItem = {
  id: 1,
  name: '内置',
  is_active: true,
  match_rules: [],
  provider_type: 'cmdb',
  input_binding: { model_id: 'resource_type', inst_uuid: 'resource_id' },
  provider_config: {},
  output_projection: [],
  on_multiple: 'first',
  namespace: 'cmdb',
  preset_key: '',
  is_builtin: false,
  created_at: '',
};

describe('告警丰富出参投影', () => {
  it('新建规则默认只有 owner，并拉取应用/应用系统字段', async () => {
    render(<OperateModal open onClose={() => undefined} />);
    await waitFor(() => expect(api.getCmdbContextFields).toHaveBeenCalledTimes(1));
    expect(screen.getAllByDisplayValue('owner')).toHaveLength(2);
    expect(screen.queryByDisplayValue('business_system')).toBeNull();
  });

  it('CMDB 不可用时仍可编辑投影', async () => {
    api.getCmdbContextFields.mockRejectedValue(new Error('cmdb down'));
    render(<OperateModal open onClose={() => undefined} />);
    await waitFor(() => expect(api.getCmdbContextFields).toHaveBeenCalled());
    expect(screen.getAllByDisplayValue('owner')).toHaveLength(2);
  });

  it('编辑未重命名的带点字段时右侧带来源名', async () => {
    render(
      <OperateModal
        open
        onClose={() => undefined}
        currentRow={{
          ...baseRow,
          output_projection: [{ source: 'application.inst_name' }],
        }}
      />
    );
    await waitFor(() =>
      expect(screen.getAllByDisplayValue('application.inst_name')).toHaveLength(2)
    );
  });

  it('已改过的重命名不会被来源字段覆盖', async () => {
    render(
      <OperateModal
        open
        onClose={() => undefined}
        currentRow={{
          ...baseRow,
          output_projection: [{ source: 'application.inst_name', as: 'app_name' }],
        }}
      />
    );
    await waitFor(() => expect(screen.getByDisplayValue('app_name')).toBeTruthy());
    expect(screen.getByDisplayValue('application.inst_name')).toBeTruthy();
    expect(screen.queryAllByDisplayValue('application.inst_name')).toHaveLength(1);
  });

  it('改左侧来源且右侧仍跟随时会同步重命名', async () => {
    render(<OperateModal open onClose={() => undefined} />);
    await waitFor(() => expect(screen.getAllByDisplayValue('owner')).toHaveLength(2));
    fireEvent.change(screen.getAllByDisplayValue('owner')[0], {
      target: { value: 'application.inst_name' },
    });
    await waitFor(() =>
      expect(screen.getAllByDisplayValue('application.inst_name')).toHaveLength(2)
    );
  });

  it('责任人来源下拉使用出参投影的重命名字段', async () => {
    render(
      <OperateModal
        open
        onClose={() => undefined}
        currentRow={{
          ...baseRow,
          output_projection: [
            { source: 'operator' },
            { source: 'bak_operator', as: 'bak_operator' },
            { source: 'application.operator', as: 'app_operator' },
          ],
          provider_config: { owner_fields: ['app_operator'] },
        }}
      />
    );
    await waitFor(() => expect(screen.getByDisplayValue('application.operator')).toBeTruthy());
    fireEvent.mouseDown(screen.getByLabelText('settings.enrichmentOwnerFields'));
    expect(await screen.findByText('operator', { selector: '.ant-select-item-option-content' })).toBeTruthy();
    expect(screen.getByText('bak_operator', { selector: '.ant-select-item-option-content' })).toBeTruthy();
    expect(
      screen.getByText('app_operator (application.operator)', {
        selector: '.ant-select-item-option-content',
      })
    ).toBeTruthy();
  });
});
