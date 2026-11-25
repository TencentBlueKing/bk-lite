import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InstallConfig from '../index';

const { getPackages, getControllerList } = vi.hoisted(() => ({
  getPackages: vi.fn(),
  getControllerList: vi.fn()
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      (
        {
          'node-manager.cloudregion.Configuration.system': '操作系统',
          'node-manager.cloudregion.node.cpuArchitecture': 'CPU架构',
          'node-manager.cloudregion.node.installationMethod': '安装方式',
          'node-manager.cloudregion.node.bulkInstall': '批量命令',
          'node-manager.cloudregion.node.remoteInstall': '远程安装',
          'node-manager.cloudregion.node.manualInstall': '手动安装',
          'node-manager.cloudregion.node.sidecarVersion': '控制器版本',
          'node-manager.cloudregion.node.bulkSidecarVersionDes':
            '版本按所选 CPU 架构列出',
          'common.pleaseSelect': '请选择',
          'common.required': '必填',
          'common.cancel': '取消',
          'node-manager.cloudregion.node.bulkGenerateCommand': '生成命令',
          'node-manager.cloudregion.node.toInstall': '安装'
        } as Record<string, string>
      )[key] || key
  })
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ isLoading: false })
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: (key: string) =>
      key === 'cloud_region_id' ? '1' : key === 'name' ? 'default' : null
  })
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({
    groups: [],
    groupTree: [],
    selectedGroup: { id: 1 }
  })
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({ clientData: [] })
}));

vi.mock('@/app/node-manager/api', () => ({
  default: () => ({
    installController: vi.fn(),
    getNodeList: vi.fn(),
    getPackages
  })
}));

vi.mock('@/app/node-manager/api/useControllerApi', () => ({
  default: () => ({
    manualInstallController: vi.fn(),
    getControllerList,
    createBulkInstall: vi.fn()
  })
}));

vi.mock('@/components/custom-table', () => ({
  default: () => <div data-testid="nodes" />
}));

vi.mock('../batchEditModal', () => ({
  default: () => null
}));

vi.mock('../excelImportModal', () => ({
  default: () => null
}));

describe('bulk install architecture field', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false
      })
    });
    getPackages.mockReset();
    getControllerList.mockReset();
    getControllerList.mockResolvedValue([
      { os: 'linux', cpu_architecture: 'x86_64' },
      { os: 'linux', cpu_architecture: 'arm64' }
    ]);
    getPackages.mockImplementation(async (params: { cpu_architecture?: string }) => {
      if (params.cpu_architecture === 'arm64') {
        return [{ id: 2, version: '1.0.0-arm', os: 'linux', cpu_architecture: 'arm64' }];
      }
      return [{ id: 1, version: '1.0.0', os: 'linux', cpu_architecture: 'x86_64' }];
    });
  });

  it('keeps CPU architecture visible and filters controller versions after bulk command is selected', async () => {
    const user = userEvent.setup();
    render(<InstallConfig onNext={vi.fn()} cancel={vi.fn()} />);

    expect(await screen.findByText('批量命令')).toBeTruthy();
    await waitFor(() => {
      expect(getPackages).toHaveBeenCalledWith(
        expect.objectContaining({
          os: 'linux',
          cpu_architecture: 'x86_64',
          type: 'controller',
          object: 'Controller'
        })
      );
    });

    await user.click(screen.getByText('批量命令'));

    expect(screen.getByText('CPU架构')).toBeTruthy();
    expect(screen.getByText('x86_64')).toBeTruthy();
    expect(screen.getByText('ARM64')).toBeTruthy();
    expect(screen.getByText('版本按所选 CPU 架构列出')).toBeTruthy();

    await user.click(screen.getByText('ARM64'));

    await waitFor(() => {
      expect(getPackages).toHaveBeenCalledWith(
        expect.objectContaining({
          os: 'linux',
          cpu_architecture: 'arm64',
          type: 'controller',
          object: 'Controller'
        })
      );
    });
  });
});
