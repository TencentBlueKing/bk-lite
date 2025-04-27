import { useTranslation } from '@/utils/i18n';
import { useMemo } from 'react';
import { SegmentedItem } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';
import type { MenuProps } from 'antd';

const useTelegrafMap = (): Record<string, Record<string, string>> => {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      1: {
        color: '#b2b5bd',
        text: t('node-manager.cloudregion.node.notInstalled'),
      },
      0: {
        color: '#2dcb56',
        text: t('node-manager.cloudregion.node.running'),
      },
      2: {
        color: '#ea3636',
        text: t('node-manager.cloudregion.node.error'),
      },
    }),
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
      running: {
        color: 'var(--color-text-2)',
        text: t('node-manager.cloudregion.node.running'),
      },
      runningUninstall: {
        color: 'var(--color-text-2)',
        text: t('node-manager.cloudregion.node.running'),
      },
      finished: {
        color: '#2dcb56',
        text: t('node-manager.cloudregion.node.successInstall'),
      },
      finishedUninstall: {
        color: '#2dcb56',
        text: t('node-manager.cloudregion.node.successInstall'),
      },
      failed: {
        color: '#ea3636',
        text: t('node-manager.cloudregion.node.failInstall'),
      },
      failedUninstall: {
        color: '#ea3636',
        text: t('node-manager.cloudregion.node.failUninstall'),
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

const useCollectoritems = (): MenuProps['items'] => {
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

const useSidecaritems = (): MenuProps['items'] => {
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

const OPERATE_SYSTEMS: SegmentedItem[] = [
  {
    label: 'Linux',
    value: 'linux',
  },
  {
    label: 'Windows',
    value: 'windows',
  },
];

const BATCH_FIELD_MAPS: Record<string, string> = {
  os: 'operateSystem',
  organizations: 'organaziton',
  username: 'loginAccount',
  port: 'loginPort',
  password: 'loginPassword',
};

export {
  useTelegrafMap,
  useInstallWays,
  useInstallMap,
  useSidecaritems,
  useCollectoritems,
  OPERATE_SYSTEMS,
  BATCH_FIELD_MAPS,
};
