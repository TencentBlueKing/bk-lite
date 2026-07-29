'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Drawer, Empty, Segmented, Space, Steps, Table, Tag, Tooltip } from 'antd';
import { Alert } from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import type {
  IncidentIMGroup,
  IncidentIMMember,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
} from '@/app/alarm/types/incidents';
import {
  getInitialMemberFilter,
  resolveMemberQueryVisibility,
  settleMemberDrawerRequest,
} from './controller';
import { deriveMemberDrawerModel } from './viewModel';

interface IMGroupMemberDrawerProps {
  open: boolean;
  group: IncidentIMGroup;
  loading: boolean;
  retryLoading: boolean;
  getIncidentIMMembers: (
    params: IncidentIMMemberListParams,
  ) => Promise<IncidentIMMemberList | null>;
  cancelMemberRequest: () => void;
  onRetry: (username?: string) => Promise<void>;
  onClose: () => void;
}

const creationStages = ['queued', 'creating_chat', 'adding_members', 'sending_summary'] as const;

export const IMGroupMemberDrawer = ({
  open,
  group,
  loading,
  retryLoading,
  getIncidentIMMembers,
  cancelMemberRequest,
  onRetry,
  onClose,
}: IMGroupMemberDrawerProps) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const pendingCount = group.member_summary.total - group.member_summary.joined;
  const [filter, setFilter] = useState<IncidentIMMemberListParams['filter']>(
    getInitialMemberFilter(pendingCount),
  );
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20 });
  const [members, setMembers] = useState<IncidentIMMemberList>({ count: 0, items: [] });
  const [memberError, setMemberError] = useState<unknown | null>(null);
  const wasOpenRef = useRef(false);

  const loadMembers = useCallback(async () => {
    setMembers({ count: 0, items: [] });
    setMemberError(null);
    try {
      const value = await getIncidentIMMembers({
        filter,
        page: pagination.page,
        page_size: pagination.pageSize as 10 | 20 | 50 | 100,
      });
      if (value) {
        const next = settleMemberDrawerRequest(
          { data: { count: 0, items: [] }, error: null },
          { data: value },
        );
        setMembers(next.data);
        setMemberError(next.error);
      }
    } catch (error) {
      const next = settleMemberDrawerRequest(
        { data: { count: 0, items: [] }, error: null },
        { error },
      );
      setMembers(next.data);
      setMemberError(next.error);
    }
  }, [filter, getIncidentIMMembers, pagination]);

  useEffect(() => {
    const next = resolveMemberQueryVisibility(
      wasOpenRef.current,
      open,
      {
        filter,
        page: pagination.page,
        pageSize: pagination.pageSize as 10 | 20 | 50 | 100,
      },
      pendingCount,
    );
    wasOpenRef.current = open;
    if (!open) return;
    setFilter(next.filter);
    setPagination({ page: next.page, pageSize: next.pageSize });
    // This transition intentionally reads the prior query once, then preserves it while open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pendingCount]);

  useEffect(() => {
    if (!open || ['pending_create', 'creating', 'create_failed'].includes(group.status)) return;
    void loadMembers();
  }, [
    group.last_sync_at,
    group.member_summary.adding,
    group.member_summary.failed,
    group.member_summary.joined,
    group.member_summary.pending,
    group.member_summary.waiting,
    group.status,
    loadMembers,
    open,
  ]);

  const closeDrawer = () => {
    cancelMemberRequest();
    onClose();
  };

  const columns: TableColumnsType<IncidentIMMember> = [
    {
      title: t('incidents.imGroup.member'),
      key: 'member',
      render: (_, member) => (
        <div className="min-w-0">
          <Tooltip title={`${member.display_name} (${member.username})`}>
            <div className="truncate font-medium">{member.display_name}</div>
          </Tooltip>
          <div className="truncate text-xs text-[var(--color-text-3)]">{member.username}</div>
        </div>
      ),
    },
    {
      title: t('incidents.imGroup.role'),
      dataIndex: 'role',
      render: role => t(`incidents.imGroup.roleValue.${role}`),
    },
    {
      title: t('incidents.imGroup.memberStatus'),
      key: 'status',
      render: (_, member) => (
        <Space direction="vertical" size={0}>
          <Tag>{t(`incidents.imGroup.mapping.${member.mapping_status}`)}</Tag>
          <Tag>{t(`incidents.imGroup.memberStatusValue.${member.sync_status}`)}</Tag>
          {drawerModel.showMappingRepair
            && ['unmapped', 'conflict'].includes(member.mapping_status)
            && (
              <Button
                type="link"
                size="small"
                href="/system-manager/channel/im-notification"
                target="_blank"
                rel="noopener noreferrer"
                className="p-0"
              >
                {t('incidents.imGroup.fixMapping')}
              </Button>
            )}
        </Space>
      ),
    },
    {
      title: t('incidents.imGroup.error'),
      key: 'error',
      render: (_, member) => (
        <div className="break-words">
          {member.error_message || t('incidents.imGroup.noError')}
          {member.error_code && (
            <div className="text-xs text-[var(--color-text-3)]">{member.error_code}</div>
          )}
          {member.sync_status === 'failed' && group.permissions.can_retry && (
            <Button
              type="link"
              size="small"
              className="p-0"
              loading={retryLoading}
              disabled={retryLoading}
              onClick={() => void onRetry(member.username)}
            >
              {t('incidents.imGroup.retryMember')}
            </Button>
          )}
        </div>
      ),
    },
    {
      title: t('incidents.imGroup.updatedAt'),
      dataIndex: 'updated_at',
      render: value => value ? convertToLocalizedTime(value) : t('incidents.imGroup.notAvailable'),
    },
  ];

  const stageIndex = Math.max(0, creationStages.indexOf(
    group.current_stage as typeof creationStages[number],
  ));
  const drawerModel = deriveMemberDrawerModel(group, memberError);
  const isCreating = drawerModel.phase === 'progress';

  return (
    <Drawer
      title={t('incidents.imGroup.detailsTitle')}
      open={open}
      width="min(720px, 100vw)"
      onClose={closeDrawer}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={closeDrawer}>{t('common.close')}</Button>
          {drawerModel.canRetryPending && (
            <Button type="primary" loading={retryLoading} onClick={() => void onRetry()}>
              {t('incidents.imGroup.retry')}
            </Button>
          )}
        </div>
      }
    >
      <Space direction="vertical" size="middle" className="w-full">
        <div className="min-w-0">
          <Tooltip title={group.group_name}>
            <div className="truncate text-base font-semibold">{group.group_name}</div>
          </Tooltip>
          <div className="text-sm text-[var(--color-text-3)]">{group.channel_name}</div>
        </div>
        <div className="flex flex-wrap gap-2 tabular-nums" aria-live="polite">
          <Tag>{t(`incidents.imGroup.${drawerModel.statusLabel}`)}</Tag>
          <Tag>
            {t('incidents.imGroup.continuousStatus', undefined, {
              status: t(drawerModel.continuousSyncEnabled
                ? 'incidents.imGroup.enabled'
                : 'incidents.imGroup.disabled'),
            })}
          </Tag>
          <Tag>{t('incidents.imGroup.joinedCount', undefined, { count: String(group.member_summary.joined) })}</Tag>
          <Tag>{t('incidents.imGroup.waitingCount', undefined, { count: String(group.member_summary.waiting) })}</Tag>
          <Tag>{t('incidents.imGroup.failedCount', undefined, { count: String(group.member_summary.failed) })}</Tag>
        </div>
        {drawerModel.lastSyncAt && (
          <div className="text-sm text-[var(--color-text-3)]">
            {t('incidents.imGroup.lastSync', undefined, {
              time: convertToLocalizedTime(drawerModel.lastSyncAt),
            })}
          </div>
        )}
        {group.status_message && (
          <Alert
            type={group.status === 'create_failed' ? 'error' : 'info'}
            showIcon
            message={group.status_message}
          />
        )}
        {isCreating ? (
          <Steps
            direction="vertical"
            current={stageIndex}
            status={group.status === 'create_failed' ? 'error' : 'process'}
            items={creationStages.map(stage => ({
              title: t(`incidents.imGroup.stage.${stage}`),
            }))}
          />
        ) : (
          <>
            {drawerModel.showMemberError && (
              <Alert
                type="error"
                showIcon
                message={t('incidents.imGroup.membersLoadFailed')}
                action={
                  <Button size="small" onClick={() => void loadMembers()}>
                    {t('common.retry')}
                  </Button>
                }
              />
            )}
            <Segmented
              value={filter}
              onChange={value => {
                setFilter(value as IncidentIMMemberListParams['filter']);
                setPagination(current => ({ ...current, page: 1 }));
              }}
              options={[
                { label: t('alarmCommon.all'), value: 'all' },
                { label: t('incidents.imGroup.pendingFilter'), value: 'pending' },
                { label: t('incidents.imGroup.joinedFilter'), value: 'joined' },
              ]}
            />
            <Table
              rowKey="username"
              size="small"
              loading={loading}
              columns={columns}
              dataSource={members.items}
              locale={{ emptyText: <Empty description={t('common.noData')} /> }}
              tableLayout="fixed"
              pagination={{
                current: pagination.page,
                pageSize: pagination.pageSize,
                total: members.count,
                showSizeChanger: true,
                pageSizeOptions: [10, 20, 50, 100],
                showTotal: total => t('incidents.imGroup.memberTotal', undefined, {
                  count: String(total),
                }),
                onChange: (page, pageSize) => setPagination({ page, pageSize }),
              }}
            />
          </>
        )}
      </Space>
    </Drawer>
  );
};
