import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Button, Popconfirm } from 'antd';
import type { TableColumnsType } from 'antd';
import { TableDataItem, SegmentedItem } from '@/app/node-manager/types';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
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
        title: t('common.name'),
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

const useTelegrafMap = (): Record<string, Record<string, string>> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      1: {
        tagColor: 'default',
        color: '#b2b5bd',
        text: t('node-manager.cloudregion.node.unknown'),
      },
      0: {
        tagColor: 'success',
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.running'),
      },
      2: {
        tagColor: 'error',
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.error'),
      },
      4: {
        tagColor: 'default',
        color: '#b2b5bd',
        text: t('node-manager.cloudregion.node.stop'),
      },
      10: {
        tagColor: 'processing',
        color: '#1677ff',
        text: t('node-manager.cloudregion.node.installing'),
        engText: 'Installing',
      },
      11: {
        tagColor: 'success',
        color: '#52c41a',
        text: t('node-manager.cloudregion.node.successInstall'),
        engText: 'Installed successfully',
      },
      12: {
        tagColor: 'error',
        color: '#ff4d4f',
        text: t('node-manager.cloudregion.node.failInstall'),
        engText: 'Installation failed',
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
      //   {
      //     label: t('node-manager.cloudregion.node.uninstallCollector'),
      //     key: 'uninstallCollector',
      //   },
    ],
    [t]
  );
};

const useSidecarItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      //   {
      //     label: (
      //       <div style={{ whiteSpace: 'nowrap' }}>
      //         {t('node-manager.cloudregion.node.restartSidecar')}
      //       </div>
      //     ),
      //     key: 'restartSidecar',
      //   },
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

export {
  useColumns,
  useGroupNames,
  useTelegrafMap,
  useInstallWays,
  useInstallMap,
  useSidecarItems,
  useCollectorItems,
  useMenuItem,
};
