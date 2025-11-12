import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Button, Popconfirm } from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  LoadingOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
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
}

const useColumns = ({
  checkConfig,
  deleteNode,
}: HookParams): TableColumnsType<TableDataItem> => {
  const { showGroupNames } = useGroupNames();
  const { t } = useTranslation();

  const columns = useMemo(
    (): TableColumnsType<TableDataItem> => [
      {
        title: t('node-manager.cloudregion.node.ip'),
        dataIndex: 'ip',
        key: 'ip',
        width: 120,
      },
      {
        title: t('node-manager.cloudregion.node.nodeName'),
        dataIndex: 'name',
        key: 'name',
        width: 120,
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
        ),
      },
      {
        title: t('node-manager.cloudregion.node.system'),
        dataIndex: 'operating_system',
        key: 'operating_system',
        width: 120,
        render: (value: string) => {
          return (
            <>
              {OPERATE_SYSTEMS.find((item) => item.value === value)?.label ||
                '--'}
            </>
          );
        },
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
                {t('node-manager.cloudregion.node.checkConfig')}
              </Button>
            </Permission>
            <Permission requiredPermissions={['Delete']}>
              <Popconfirm
                className="ml-[10px]"
                title={t(`common.prompt`)}
                description={t(`node-manager.cloudregion.node.deleteNodeTips`)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => {
                  deleteNode(item);
                }}
              >
                <Button type="link" disabled={item.active}>
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            </Permission>
          </>
        ),
      },
    ],
    [checkConfig, deleteNode, t]
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
    showGroupNames,
  };
};

const useTelegrafMap = (): Record<string, Record<string, any>> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      1: {
        tagColor: 'default',
        color: '#b2b5bd',
        text: t('node-manager.cloudregion.node.unknown'),
        engText: 'Unknown',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(178, 181, 189, 0.1)' }}
          >
            <ExclamationCircleOutlined
              style={{
                color: '#b2b5bd',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      0: {
        tagColor: 'success',
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.normal'),
        engText: 'Running',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(82, 196, 26, 0.1)' }}
          >
            <CheckCircleOutlined
              style={{
                color: '#52c41a',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      2: {
        tagColor: 'error',
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.error'),
        engText: 'Failed',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(255, 77, 79, 0.1)' }}
          >
            <CloseCircleOutlined
              style={{
                color: '#ff4d4f',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      4: {
        tagColor: '',
        color: '#000000',
        text: t('node-manager.cloudregion.node.notStarted'),
        engText: 'Stopped',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.1)' }}
          >
            <StopOutlined
              style={{
                color: '#000000',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      10: {
        tagColor: 'processing',
        color: '#1677ff',
        text: t('node-manager.cloudregion.node.installing'),
        engText: 'Installing',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(22, 119, 255, 0.1)' }}
          >
            <LoadingOutlined
              style={{
                color: '#1677ff',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      11: {
        tagColor: '',
        color: '#000000',
        text: t('node-manager.cloudregion.node.notStarted'),
        engText: 'Installed',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.1)' }}
          >
            <StopOutlined
              style={{
                color: '#000000',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
      12: {
        tagColor: 'warning',
        color: '#faad14',
        text: t('node-manager.cloudregion.node.failInstall'),
        engText: 'Installation failed',
        icon: (
          <div
            className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'rgba(250, 173, 20, 0.1)' }}
          >
            <WarningOutlined
              style={{
                color: '#faad14',
                fontWeight: 'bold',
                fontSize: '12px',
              }}
            />
          </div>
        ),
      },
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
        value: 'remoteInstall',
      },
      {
        label: t('node-manager.cloudregion.node.manualInstall'),
        value: 'manualInstall',
      },
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
        text: t('node-manager.cloudregion.node.installing'),
      },
      waitingUninstall: {
        color: 'var(--color-primary)',
        text: t('node-manager.cloudregion.node.uninstalling'),
      },
      success: {
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.successInstall'),
      },
      successUninstall: {
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.successInstall'),
      },
      error: {
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.failInstall'),
      },
      errorUninstall: {
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.failUninstall'),
      },
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
        key: 'installCollector',
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
        key: 'startCollector',
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
        key: 'restartCollector',
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
        key: 'stopCollector',
      },
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
            {t('node-manager.cloudregion.node.uninstallSidecar')}
          </PermissionWrapper>
        ),
        key: 'uninstallSidecar',
      },
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
          type: 'edit',
        },
      },
      {
        key: 'delete',
        role: 'Delete',
        title: 'delete',
        config: {
          title: 'deleteform',
          type: 'delete',
        },
      },
    ],
    [t]
  );
};

const useInstallMethodMap = (): Record<string, { text: string }> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      auto: {
        text: t('node-manager.cloudregion.node.auto'),
      },
      manual: {
        text: t('node-manager.cloudregion.node.manual'),
      },
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
        lookup_expr: 'icontains',
      },
      {
        name: 'ip',
        label: t('node-manager.cloudregion.node.ip'),
        lookup_expr: 'icontains',
      },
      {
        name: 'operating_system',
        label: t('node-manager.cloudregion.node.system'),
        lookup_expr: 'in',
        options: OPERATE_SYSTEMS.map((item) => ({
          id: item.value,
          name: item.label,
        })),
      },
      {
        name: 'install_method',
        label: t('node-manager.cloudregion.node.installMethod'),
        lookup_expr: 'in',
        options: [
          { id: 'auto', name: installMethodMap['auto']?.text || 'Auto' },
          { id: 'manual', name: installMethodMap['manual']?.text || 'Manual' },
        ],
      },
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
  useFieldConfigs,
};
