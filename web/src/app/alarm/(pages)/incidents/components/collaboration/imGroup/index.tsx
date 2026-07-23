'use client';

import { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Dropdown,
  message,
  Modal,
  Skeleton,
  Tag,
  Tooltip,
} from 'antd';
import type { MenuProps } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  LinkOutlined,
  MoreOutlined,
  PauseCircleOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import PermissionWrapper from '@/components/permission';
import { isSilentRequestError } from '@/utils/request';
import type {
  CreateIncidentIMGroupParams,
  IncidentTableDataItem,
} from '@/app/alarm/types/incidents';
import { deriveIMGroupView } from './state';
import { runIMGroupAction } from './controller';
import { useIncidentIMGroup } from './useIncidentIMGroup';
import { CreateIMGroupModal } from './createModal';
import { IMGroupMemberDrawer } from './memberDrawer';
import {
  ContinuousSyncModal,
  PauseIMGroupModal,
  UnlinkIMGroupModal,
} from './confirmModals';

interface IncidentIMGroupPanelProps {
  incidentPk: string;
  incidentDetail?: IncidentTableDataItem;
  refreshVersion: number;
}

const viewIcon = {
  creating: <ClockCircleOutlined />,
  active: <CheckCircleOutlined />,
  partial: <ExclamationCircleOutlined />,
  paused: <PauseCircleOutlined />,
  incidentClosed: <PauseCircleOutlined />,
  createFailed: <ExclamationCircleOutlined />,
  degraded: <ExclamationCircleOutlined />,
} as const;

const viewTagColor = {
  creating: 'processing',
  active: 'success',
  partial: 'warning',
  paused: 'default',
  incidentClosed: 'default',
  createFailed: 'error',
  degraded: 'error',
} as const;

export const IncidentIMGroupPanel = ({
  incidentPk,
  refreshVersion,
}: IncidentIMGroupPanelProps) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const controller = useIncidentIMGroup({ incidentPk, refreshVersion });
  const [createOpen, setCreateOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pauseOpen, setPauseOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsEnabled, setSettingsEnabled] = useState(false);
  const [unlinkOpen, setUnlinkOpen] = useState(false);
  const [unlinkConfirmation, setUnlinkConfirmation] = useState('');

  const group = controller.group;
  const view = useMemo(() => group ? deriveIMGroupView(group) : null, [group]);

  const showActionError = (error: unknown) => {
    if (isSilentRequestError(error)) return;
    message.error(error instanceof Error && error.message
      ? error.message
      : t('common.saveFailed'));
  };

  const openCreate = async () => {
    try {
      await controller.loadOptions();
      setCreateOpen(true);
    } catch {
      // The request layer renders the server-safe error; keep the existing card/modal state.
    }
  };

  const submitCreate = async (params: CreateIncidentIMGroupParams) => {
    try {
      await controller.createGroup(params);
      setCreateOpen(false);
      message.success(t('incidents.imGroup.createAccepted'));
    } catch (error) {
      showActionError(error);
    }
  };

  const copyChatId = async () => {
    if (!group?.external_chat_id) return;
    try {
      await navigator.clipboard.writeText(group.external_chat_id);
      message.success(t('alarmCommon.copied'));
    } catch {
      message.error(t('incidents.imGroup.copyFailed'));
    }
  };

  const openChat = () => {
    if (!group) return;
    if (!group.open_chat_url) {
      void copyChatId();
      return;
    }
    const target = window.open(group.open_chat_url, '_blank', 'noopener,noreferrer');
    if (target) target.opener = null;
  };

  const confirmAction = (
    titleKey: string,
    contentKey: string,
    action: () => Promise<unknown>,
  ) => {
    Modal.confirm({
      title: t(titleKey),
      content: t(contentKey),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        await runIMGroupAction(
          async () => { await action(); },
          () => undefined,
          showActionError,
        );
      },
    });
  };

  const retry = async () => {
    await runIMGroupAction(
      async () => { await controller.retry(); },
      () => message.success(t('incidents.imGroup.retryAccepted')),
      showActionError,
    );
  };

  const primaryAction = () => {
    if (!group || !view) return;
    if (view.primaryAction === 'details') {
      setDrawerOpen(true);
    } else if (view.primaryAction === 'open') {
      openChat();
    } else if (view.primaryAction === 'resume') {
      confirmAction(
        'incidents.imGroup.resumeConfirmTitle',
        'incidents.imGroup.resumeConfirm',
        controller.resume,
      );
    } else {
      confirmAction(
        'incidents.imGroup.retryConfirmTitle',
        'incidents.imGroup.retryConfirm',
        retry,
      );
    }
  };

  const primaryLabel = () => {
    if (!group || !view) return '';
    if (view.primaryAction === 'details') return t('incidents.imGroup.viewProgress');
    if (view.primaryAction === 'resume') return t('incidents.imGroup.resume');
    if (view.primaryAction === 'retry') {
      return group.status === 'degraded'
        ? t('incidents.imGroup.recheck')
        : t('incidents.imGroup.retry');
    }
    return group.open_chat_url
      ? t('incidents.imGroup.openChat')
      : t('incidents.imGroup.copyChatId');
  };

  const moreItems: MenuProps['items'] = group ? [
    {
      key: 'copy',
      label: t('incidents.imGroup.copyChatId'),
      icon: <LinkOutlined />,
      onClick: () => void copyChatId(),
      disabled: !group.external_chat_id,
    },
    ...(group.permissions.can_manage ? [
      {
        key: 'settings',
        label: t('incidents.imGroup.continuousSync'),
        onClick: () => {
          setSettingsEnabled(group.continuous_sync_enabled);
          setSettingsOpen(true);
        },
      },
    ] : []),
    ...(group.permissions.can_pause ? [{
      key: 'pause',
      label: t('incidents.imGroup.pause'),
      onClick: () => setPauseOpen(true),
    }] : []),
    ...(group.permissions.can_unlink ? [{
      key: 'unlink',
      danger: true,
      label: t('incidents.imGroup.unlink'),
      onClick: () => {
        setUnlinkConfirmation('');
        setUnlinkOpen(true);
      },
    }] : []),
  ] : [];

  if (controller.groupLoading && !group) {
    return (
      <div className="mb-4 rounded-lg border border-[var(--color-border)] p-3">
        <Skeleton active paragraph={{ rows: 3 }} title={{ width: '70%' }} />
      </div>
    );
  }

  if (controller.groupError && !group) {
    return (
      <Alert
        className="mb-4"
        type="error"
        showIcon
        message={t('incidents.imGroup.loadFailed')}
        action={
          <Button size="small" onClick={() => void controller.refreshGroup()}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }

  if (!group) {
    if (!controller.createPermissionChecked || controller.optionsLoading) {
      return (
        <div className="mb-4 rounded-lg border border-[var(--color-border)] p-3">
          <Skeleton active paragraph={{ rows: 2 }} title={{ width: '70%' }} />
        </div>
      );
    }
    return (
      <div className="mb-4 rounded-lg border border-[var(--color-border)] p-3">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="font-medium">{t('incidents.imGroup.title')}</span>
          <Tag>{t('incidents.imGroup.notCreated')}</Tag>
        </div>
        <p className="text-xs text-[var(--color-text-3)]">
          {t('incidents.imGroup.emptyDescription')}
        </p>
        {controller.optionsError && (
          <Alert
            className="mb-2"
            type="error"
            showIcon
            message={t('incidents.imGroup.permissionProbeFailed')}
            action={
              <Button size="small" onClick={() => void controller.refreshCreatePermission()}>
                {t('common.retry')}
              </Button>
            }
          />
        )}
        {controller.canCreate && (
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              block
              size="small"
              type="primary"
              icon={<TeamOutlined />}
              loading={controller.optionsLoading}
              onClick={() => void openCreate()}
            >
              {t('incidents.imGroup.create')}
            </Button>
          </PermissionWrapper>
        )}
        <CreateIMGroupModal
          open={createOpen}
          options={controller.options}
          optionsChannelId={controller.optionsChannelId}
          optionsError={controller.optionsError}
          loading={controller.optionsLoading}
          submitting={controller.createLoading}
          onLoadOptions={controller.loadOptions}
          onSubmit={submitCreate}
          onCancel={() => setCreateOpen(false)}
        />
      </div>
    );
  }

  const pendingCount = group.member_summary.total - group.member_summary.joined;
  const statusLabel = t(`incidents.imGroup.${view?.label ?? 'active'}`);
  const canRunPrimary = view?.primaryAction === 'open'
    || view?.primaryAction === 'details'
    || (view?.primaryAction === 'retry' && group.permissions.can_retry)
    || (view?.primaryAction === 'resume' && group.permissions.can_resume);

  return (
    <>
      <section
        className="mb-4 rounded-lg border border-[var(--color-border)] p-3"
        aria-label={t('incidents.imGroup.title')}
      >
        <div className="flex items-start justify-between gap-2 mb-2">
          <span className="font-medium">{t('incidents.imGroup.title')}</span>
          {view && (
            <Tag icon={viewIcon[view.label]} color={viewTagColor[view.label]} className="m-0">
              {statusLabel}
            </Tag>
          )}
        </div>
        <Tooltip title={group.group_name}>
          <div className="truncate text-sm font-medium">{group.group_name}</div>
        </Tooltip>
        <Tooltip title={group.channel_name}>
          <div className="truncate text-xs text-[var(--color-text-3)] mb-2">{group.channel_name}</div>
        </Tooltip>
        <div className="text-xs text-[var(--color-text-2)] space-y-1 tabular-nums" aria-live="polite">
          <div>
            {t('incidents.imGroup.summary', undefined, {
              joined: String(group.member_summary.joined),
              waiting: String(group.member_summary.waiting),
              failed: String(group.member_summary.failed),
            })}
          </div>
          <div>
            {t('incidents.imGroup.continuousStatus', undefined, {
              status: t(group.continuous_sync_enabled
                ? 'incidents.imGroup.enabled'
                : 'incidents.imGroup.disabled'),
            })}
          </div>
          {group.last_sync_at && (
            <div>
              {t('incidents.imGroup.lastSync', undefined, {
                time: convertToLocalizedTime(group.last_sync_at),
              })}
            </div>
          )}
          <div>{t(`incidents.imGroup.description.${view?.label ?? 'active'}`, undefined, {
            count: String(pendingCount),
          })}</div>
          {group.status_message && <div className="break-words">{group.status_message}</div>}
          {view?.syncingCount && (
            <div>{t('incidents.imGroup.syncing', undefined, {
              count: String(view.syncingCount),
            })}</div>
          )}
        </div>
        <div className="flex items-center gap-1 mt-3">
          <Button size="small" onClick={() => setDrawerOpen(true)}>
            {t('incidents.imGroup.viewDetails')}
          </Button>
          {view?.primaryAction !== 'details' && canRunPrimary && (
            view?.primaryAction === 'open' ? (
              <Button size="small" type="primary" onClick={primaryAction}>
                {primaryLabel()}
              </Button>
            ) : (
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  size="small"
                  type="primary"
                  loading={controller.actionLoadingKey === view?.primaryAction}
                  onClick={primaryAction}
                >
                  {primaryLabel()}
                </Button>
              </PermissionWrapper>
            )
          )}
          {!group.permissions.can_manage
            && view?.primaryAction !== 'open'
            && Boolean(group.external_chat_id)
            && (
              <Button size="small" type="primary" onClick={openChat}>
                {group.open_chat_url
                  ? t('incidents.imGroup.openChat')
                  : t('incidents.imGroup.copyChatId')}
              </Button>
            )}
          {group.permissions.can_manage && (
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Dropdown menu={{ items: moreItems }} trigger={['click']} placement="bottomRight">
                <Button
                  size="small"
                  type="text"
                  icon={<MoreOutlined aria-hidden="true" />}
                  aria-label={t('common.more')}
                />
              </Dropdown>
            </PermissionWrapper>
          )}
        </div>
      </section>

      <IMGroupMemberDrawer
        open={drawerOpen}
        group={group}
        loading={controller.memberLoading}
        retryLoading={controller.actionLoadingKey === 'retry'}
        getIncidentIMMembers={controller.getMembers}
        cancelMemberRequest={controller.cancelMemberRequest}
        onRetry={retry}
        onClose={() => setDrawerOpen(false)}
      />
      <PauseIMGroupModal
        open={pauseOpen}
        loading={controller.actionLoadingKey === 'pause'}
        onCancel={() => setPauseOpen(false)}
        onConfirm={async () => {
          await runIMGroupAction(
            async () => { await controller.pause(); },
            () => setPauseOpen(false),
            showActionError,
          );
        }}
      />
      <ContinuousSyncModal
        open={settingsOpen}
        enabled={settingsEnabled}
        loading={controller.actionLoadingKey === 'settings'}
        onChange={setSettingsEnabled}
        onCancel={() => setSettingsOpen(false)}
        onConfirm={async () => {
          await runIMGroupAction(
            async () => { await controller.updateContinuousSync(settingsEnabled); },
            () => setSettingsOpen(false),
            showActionError,
          );
        }}
      />
      <UnlinkIMGroupModal
        open={unlinkOpen}
        groupName={group.group_name}
        confirmation={unlinkConfirmation}
        loading={controller.actionLoadingKey === 'unlink'}
        onConfirmationChange={setUnlinkConfirmation}
        onCancel={() => setUnlinkOpen(false)}
        onConfirm={async () => {
          await runIMGroupAction(
            async () => { await controller.unlink(group.group_name); },
            () => {
              setUnlinkOpen(false);
              setDrawerOpen(false);
              message.success(t('incidents.imGroup.unlinkSuccess'));
            },
            showActionError,
          );
        }}
      />
    </>
  );
};

export default IncidentIMGroupPanel;
