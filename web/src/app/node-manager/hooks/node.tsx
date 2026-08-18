import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Button } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  LoadingOutlined,
  WarningOutlined,
  PauseCircleOutlined
} from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { TableDataItem, SegmentedItem } from '@/app/node-manager/types';
import { FieldConfig } from '@/app/node-manager/types/node';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import type { MenuProps } from 'antd';
interface HookParams {
  checkConfig: (row: TableDataItem) => void;
  deleteNode: (row: TableDataItem) => void;
  editNode: (row: TableDataItem) => void;
}

const useColumns = ({
  checkConfig,
  deleteNode,
  editNode
}: HookParams): TableColumnsType<TableDataItem> => {
  const { showGroupNames } = useGroupNames();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { t } = useTranslation();

  const columns = useMemo(
    (): TableColumnsType<TableDataItem> => [
      {
        title: t('node-manager.cloudregion.node.ip'),
        dataIndex: 'ip',
        key: 'ip',
        width: 120
      },
      {
        title: t('node-manager.cloudregion.node.nodeName'),
        dataIndex: 'name',
        key: 'name',
        width: 120
      },
      {
        title: t('node-manager.cloudregion.node.group'),
        dataIndex: 'organization',
        key: 'organization',
        width: 120,
        render: (_, { organization }) => (
          <EllipsisWithTooltip
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            text={showGroupNames(organization)}
          />
        )
      },
      {
        title: t('node-manager.cloudregion.node.lastReportTime'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 160,
        render: (text: string) => {
          return text ? convertToLocalizedTime(text) : '--';
        }
      },
      {
        title: t('common.actions'),
        key: 'action',
        dataIndex: 'action',
        width: 200,
        fixed: 'right',
        render: (key, item) => (
          <>
            <Permission requiredPermissions={['View']}>
              <Button type="link" onClick={() => checkConfig(item)}>
                {t('common.detail')}
              </Button>
            </Permission>
            <Permission className="ml-[10px]" requiredPermissions={['Edit']}>
              <Button type="link" onClick={() => editNode(item)}>
                {t('common.edit')}
              </Button>
            </Permission>
            <Permission requiredPermissions={['Delete']}>
              <Button
                className="ml-[10px]"
                type="link"
                disabled={item.active}
                onClick={() => deleteNode(item)}
              >
                {t('common.delete')}
              </Button>
            </Permission>
          </>
        )
      }
    ],
    [checkConfig, deleteNode, editNode, t]
  );
  return columns;
};

const useGroupNames = () => {
  const commonContext = useUserInfoContext();
  const showGroupNames = (ids: string[]) => {
    if (!ids?.length) return '--';
    const groups = commonContext?.groups || [];
    const groupNames = ids.map(
      (item) => groups.find((group) => Number(group.id) === Number(item))?.name
    );
    return groupNames.filter((item) => !!item).join(',') || '--';
  };
  return {
    showGroupNames
  };
};

const useTelegrafMap = (): Record<string, Record<string, any>> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      1: {
        tagColor: 'default',
        color: 'var(--color-text-3)',
        text: t('node-manager.cloudregion.node.unknown'),
        engText: 'Unknown',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-text-3)_10%,transparent)]">
            <ExclamationCircleOutlined className="text-[12px] font-bold text-[var(--color-text-3)]" />
          </div>
        )
      },
      0: {
        tagColor: 'success',
        color: 'var(--color-success)',
        text: t('node-manager.cloudregion.node.normal'),
        engText: 'Running',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-success)_10%,transparent)]">
            <CheckCircleOutlined className="text-[12px] font-bold text-[var(--color-success)]" />
          </div>
        )
      },
      2: {
        tagColor: 'error',
        color: 'var(--color-fail)',
        text: t('node-manager.cloudregion.node.error'),
        engText: 'Failed',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-fail)_10%,transparent)]">
            <CloseCircleOutlined className="text-[12px] font-bold text-[var(--color-fail)]" />
          </div>
        )
      },
      3: {
        tagColor: 'warning',
        color: 'var(--color-warning)',
        text: t('node-manager.cloudregion.node.stopped'),
        engText: 'Stopped',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-warning)_10%,transparent)]">
            <PauseCircleOutlined className="text-[12px] font-bold text-[var(--color-warning)]" />
          </div>
        )
      },
      4: {
        tagColor: '',
        color: 'var(--color-text-1)',
        text: t('node-manager.cloudregion.node.notStarted'),
        engText: 'Stopped',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-text-1)_10%,transparent)]">
            <StopOutlined className="text-[12px] font-bold text-[var(--color-text-1)]" />
          </div>
        )
      },
      10: {
        tagColor: 'processing',
        color: 'var(--color-primary)',
        text: t('node-manager.cloudregion.node.installing'),
        engText: 'Installing',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-primary)_10%,transparent)]">
            <LoadingOutlined className="text-[12px] font-bold text-[var(--color-primary)]" />
          </div>
        )
      },
      11: {
        tagColor: '',
        color: 'var(--color-text-1)',
        text: t('node-manager.cloudregion.node.notStarted'),
        engText: 'Installed',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-text-1)_10%,transparent)]">
            <StopOutlined className="text-[12px] font-bold text-[var(--color-text-1)]" />
          </div>
        )
      },
      12: {
        tagColor: 'warning',
        color: 'var(--color-warning)',
        text: t('node-manager.cloudregion.node.failInstall'),
        engText: 'Installation failed',
        icon: (
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--color-warning)_10%,transparent)]">
            <WarningOutlined className="text-[12px] font-bold text-[var(--color-warning)]" />
          </div>
        )
      }
    }),
    [t]
  );
};

const useInstallWays = (): SegmentedItem[] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: t('node-manager.cloudregion.node.remoteInstall'),
        value: 'remoteInstall'
      },
      {
        label: t('node-manager.cloudregion.node.manualInstall'),
        value: 'manualInstall'
      }
    ],
    [t]
  );
};

const useInstallMap = (): Record<string, Record<string, string>> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      waiting: {
        color: 'var(--color-primary)',
        text: t('node-manager.cloudregion.node.installing')
      },
      waitingUninstall: {
        color: 'var(--color-primary)',
        text: t('node-manager.cloudregion.node.uninstalling')
      },
      success: {
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.successInstall')
      },
      successUninstall: {
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.successUninstall')
      },
      error: {
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.failInstall')
      },
      errorUninstall: {
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.failUninstall')
      }
    }),
    [t]
  );
};

const useCollectorItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['OperateCollector']}
          >
            {t('node-manager.cloudregion.node.installCollector')}
          </PermissionWrapper>
        ),
        key: 'installCollector'
      },
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['OperateCollector']}
          >
            {t('node-manager.cloudregion.node.startCollector')}
          </PermissionWrapper>
        ),
        key: 'startCollector'
      },
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['OperateCollector']}
          >
            {t('node-manager.cloudregion.node.restartCollector')}
          </PermissionWrapper>
        ),
        key: 'restartCollector'
      },
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['OperateCollector']}
          >
            {t('node-manager.cloudregion.node.stopCollector')}
          </PermissionWrapper>
        ),
        key: 'stopCollector'
      }
    ],
    [t]
  );
};

const useSidecarItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['UninstallController']}
          >
            {t('node-manager.cloudregion.node.uninstallController')}
          </PermissionWrapper>
        ),
        key: 'uninstallController'
      }
    ],
    [t]
  );
};

const useMenuItem = () => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        key: 'edit',
        role: 'Edit',
        title: 'edit',
        config: {
          title: 'editform',
          type: 'edit'
        }
      },
      {
        key: 'delete',
        role: 'Delete',
        title: 'delete',
        config: {
          title: 'deleteform',
          type: 'delete'
        }
      }
    ],
    [t]
  );
};

const useInstallMethodMap = (): Record<string, { text: string }> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      auto: {
        text: t('node-manager.cloudregion.node.auto')
      },
      manual: {
        text: t('node-manager.cloudregion.node.manual')
      }
    }),
    [t]
  );
};

const useFieldConfigs = (): FieldConfig[] => {
  const { t } = useTranslation();
  const installMethodMap = useInstallMethodMap();

  return useMemo(
    () => [
      {
        name: 'name',
        label: t('node-manager.cloudregion.node.nodeName'),
        lookup_expr: 'icontains'
      },
      {
        name: 'ip',
        label: t('node-manager.cloudregion.node.ip'),
        lookup_expr: 'icontains'
      },
      {
        name: 'operating_system',
        label: t('node-manager.cloudregion.node.system'),
        lookup_expr: 'in',
        options: OPERATE_SYSTEMS.map((item) => ({
          id: item.value,
          name: item.label
        }))
      },
      {
        name: 'install_method',
        label: t('node-manager.cloudregion.node.installMethod'),
        lookup_expr: 'in',
        options: [
          { id: 'auto', name: installMethodMap['auto']?.text || 'Auto' },
          { id: 'manual', name: installMethodMap['manual']?.text || 'Manual' }
        ]
      },
      {
        name: 'upgradeable',
        label: t('node-manager.cloudregion.node.controllerUpgradeable'),
        lookup_expr: 'bool',
        options: [
          { id: 'true', name: t('common.yes') },
          { id: 'false', name: t('common.no') }
        ]
      },
      {
        name: 'cpu_architecture',
        label: t('node-manager.cloudregion.node.cpuArchitecture'),
        lookup_expr: 'in',
        options: [
          { id: 'x86_64', name: 'X86_64' },
          { id: 'arm64', name: 'ARM64' }
        ]
      }
    ],
    [t, installMethodMap]
  );
};

export {
  useColumns,
  useGroupNames,
  useTelegrafMap,
  useInstallWays,
  useInstallMap,
  useSidecarItems,
  useCollectorItems,
  useMenuItem,
  useInstallMethodMap,
  useFieldConfigs
};
