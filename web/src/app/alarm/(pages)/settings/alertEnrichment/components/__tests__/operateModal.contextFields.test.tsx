import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OperateModal from '../operateModal';

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

describe('告警丰富出参投影', () => {
  it('新建规则默认只有 owner，并拉取应用/应用系统字段', async () => {
    render(<OperateModal open onClose={() => undefined} />);
    await waitFor(() => expect(api.getCmdbContextFields).toHaveBeenCalledTimes(1));
    expect(screen.getByDisplayValue('owner')).toBeTruthy();
    expect(screen.queryByDisplayValue('business_system')).toBeNull();
  });

  it('CMDB 不可用时仍可编辑投影', async () => {
    api.getCmdbContextFields.mockRejectedValue(new Error('cmdb down'));
    render(<OperateModal open onClose={() => undefined} />);
    await waitFor(() => expect(api.getCmdbContextFields).toHaveBeenCalled());
    expect(screen.getByDisplayValue('owner')).toBeTruthy();
  });
});
