'use client';

import { useCallback, useMemo, useState } from 'react';
import {
  DeleteOutlined,
  PlusOutlined,
  SearchOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Select,
  type TableColumnsType,
} from 'antd';

import { useRumQueries, type RumEraseJob } from '@/app/rum/api';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import RumPermission from '@/app/rum/components/rum-permission';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import CustomTable from '@/components/custom-table';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useTranslation } from '@/utils/i18n';

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || '—';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function RumCompliancePage() {
  const { t } = useTranslation();
  const { listApplications, listEraseJobs, eraseCompliance, authReady } = useRumQueries();

  const [selectedApp, setSelectedApp] = useState('all');
  const [searchUser, setSearchUser] = useState('');
  const [records, setRecords] = useState<RumEraseJob[]>([]);
  const [applications, setApplications] = useState<string[]>([]);
  const [pending, setPending] = useState(true);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [formApp, setFormApp] = useState('');
  const [formUserId, setFormUserId] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadJobs = useCallback(async () => {
    setPending(true);
    try {
      const params: Record<string, string> = {};
      if (selectedApp && selectedApp !== 'all') params.application = selectedApp;
      setRecords(await listEraseJobs(params));
    } catch {
      setRecords([]);
    } finally {
      setPending(false);
    }
  }, [listEraseJobs, selectedApp]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      const params: Record<string, string> = {};
      if (selectedApp && selectedApp !== 'all') params.application = selectedApp;
      void listEraseJobs(params)
        .then((next) => {
          if (!isCancelled()) setRecords(next);
        })
        .catch(() => {
          if (!isCancelled()) setRecords([]);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listEraseJobs, selectedApp],
  );

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void listApplications()
        .then((items) => {
          if (isCancelled()) return;
          const names = items.map((item) => item.application).filter(Boolean);
          setApplications(names);
          setFormApp((prev) => prev || names[0] || '');
        })
        .catch(() => {
          if (!isCancelled()) setApplications([]);
        });
    },
    [listApplications],
  );

  const filteredRecords = useMemo(() => {
    const needle = searchUser.trim().toLowerCase();
    if (!needle) return records;
    return records.filter((r) => r.endUserId.toLowerCase().includes(needle));
  }, [records, searchUser]);
  const table = useRumClientPager(filteredRecords, `${selectedApp}|${searchUser}`);

  async function handleCreateErasure() {
    if (!formApp.trim() || !formUserId.trim()) return;
    setSubmitting(true);
    try {
      await eraseCompliance({
        application: formApp.trim(),
        endUserId: formUserId.trim(),
      });
      setFormUserId('');
      setDrawerOpen(false);
      await loadJobs();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setSubmitting(false);
    }
  }

  const columns = useMemo<TableColumnsType<RumEraseJob>>(
    () => [
      {
        title: t('rum.compliance.createdAt', '提交时间'),
        key: 'createdAt',
        width: 160,
        render: (_: unknown, r: RumEraseJob) => (
          <span className="font-mono tabular-nums">
            {formatWhen(r.createdAt)}
          </span>
        ),
      },
      {
        title: t('rum.applications.application', '应用'),
        key: 'application',
        width: 160,
        render: (_: unknown, r: RumEraseJob) => (
          <span className="font-mono">{r.application}</span>
        ),
      },
      {
        title: t('rum.compliance.endUserId', '终端用户 ID'),
        key: 'endUserId',
        ellipsis: true,
        render: (_: unknown, r: RumEraseJob) => (
          <span className="truncate font-mono">{r.endUserId}</span>
        ),
      },
      {
        title: t('rum.compliance.scope', '删除范围'),
        key: 'scope',
        width: 160,
        render: () => (
          <span>
            {t('rum.compliance.scopeAll', '全部 RUM 数据')}
          </span>
        ),
      },
      {
        title: t('rum.compliance.status', '状态'),
        key: 'status',
        width: 96,
        render: (_: unknown, r: RumEraseJob) => {
          // Ledger status follows the controller operation: accepted/pending →
          // in flight, completed/purged → done, failed → needs attention.
          const done = r.status === 'purged' || r.status === 'completed';
          const failed = r.status === 'failed';
          return (
            <SemanticBadge
              label={
                done
                  ? t('rum.compliance.statusPurged', '已清除')
                  : failed
                    ? t('rum.compliance.statusFailed', '失败')
                    : t('rum.compliance.statusAccepted', '已受理')
              }
              {...toneSemanticPalette(done ? 'neutral' : failed ? 'danger' : 'success')}
            />
          );
        },
      },
    ],
    [t],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.compliance.title', '合规删除')}</h1>
      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            trailing={
              <>
                <Select
                  value={selectedApp}
                  onChange={setSelectedApp}
                  className="min-w-40 w-44"
                  options={[
                    { value: 'all', label: t('rum.filter.allApps', '全部应用') },
                    ...applications.map((app) => ({ value: app, label: app })),
                  ]}
                />
                <Input
                  value={searchUser}
                  onChange={(e) => setSearchUser(e.target.value)}
                  placeholder={t('rum.compliance.searchPlaceholder', '按终端用户 ID 搜索')}
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  className="!h-8 w-60 !items-center !py-0"
                  allowClear
                />
                <RumPermission resource="compliance" action="Operate">
                  <Button
                    type="primary"
                    danger
                    icon={<PlusOutlined aria-hidden="true" />}
                    onClick={() => setDrawerOpen(true)}
                  >
                    {t('rum.compliance.create', '提交删除请求')}
                  </Button>
                </RumPermission>
              </>
            }
          />
        }
      >
        {!pending && filteredRecords.length === 0 ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <Empty
              description={
                <div className="flex flex-col gap-1">
                  <span>{t('rum.compliance.empty', '还没有删除记录')}</span>
                  <span className="text-xs text-[var(--color-text-3)]">
                    {t(
                      'rum.compliance.emptyHint',
                      '提交后会写入服务端审计台账，可在此追踪受理状态。',
                    )}
                  </span>
                </div>
              }
            />
          </div>
        ) : pending && records.length === 0 ? (
          <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
        ) : filteredRecords.length > 0 ? (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumEraseJob>
              rowKey="id"
              size="middle"
              tableLayout="fixed"
              autoScrollX={false}
              dataSource={table.rows}
              columns={columns}
              pagination={{
                current: table.pagination.current,
                pageSize: table.pagination.pageSize,
                total: table.pagination.total,
                showSizeChanger: table.pagination.showSizeChanger,
                onChange: table.pagination.onChange,
              }}
            />
          </div>
        ) : null}
      </RumSingleWorkbench>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        width={480}
        title={t('rum.compliance.create', '提交删除请求')}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDrawerOpen(false)}>{t('rum.common.cancel', '取消')}</Button>
            <Popconfirm
              title={t('rum.compliance.confirm', '确认提交删除？')}
              description={t(
                'rum.compliance.confirmDetail',
                '提交后将物理抹除该用户在该应用下的所有会话、错误与录屏数据。',
              )}
              onConfirm={() => void handleCreateErasure()}
              okText={t('rum.compliance.submit', '提交删除')}
              cancelText={t('rum.common.cancel', '取消')}
              okButtonProps={{ danger: true, loading: submitting }}
              disabled={!formApp.trim() || !formUserId.trim() || submitting}
            >
              <Button
                type="primary"
                danger
                loading={submitting}
                disabled={!formApp.trim() || !formUserId.trim()}
              >
                {t('rum.compliance.submit', '提交删除')}
              </Button>
            </Popconfirm>
          </div>
        }
      >
        <div className="flex flex-col gap-5">
          <Alert
            type="warning"
            showIcon
            icon={<WarningOutlined className="text-[var(--theme-color-status-warning)]" />}
            message={t(
              'rum.compliance.warning',
              '此操作不可逆。仅在合规要求下删除指定终端用户的 RUM 数据。',
            )}
            className="text-xs"
          />

          <Form layout="vertical" requiredMark={false}>
            <Form.Item label={t('rum.applications.application', '应用')} className="mb-4">
              {applications.length > 0 ? (
                <Select
                  value={formApp || undefined}
                  onChange={setFormApp}
                  placeholder={t('rum.compliance.selectApplication', '选择应用')}
                  options={applications.map((item) => ({ value: item, label: item }))}
                  className="w-full"
                />
              ) : (
                <Input
                  value={formApp}
                  onChange={(e) => setFormApp(e.target.value)}
                  placeholder="storefront"
                />
              )}
            </Form.Item>

            <Form.Item label={t('rum.compliance.endUserId', '终端用户 ID')} className="mb-4">
              <Input
                value={formUserId}
                onChange={(e) => setFormUserId(e.target.value)}
                placeholder={t(
                  'rum.compliance.endUserPlaceholder',
                  '例如：user-123 或匿名会话识别 ID',
                )}
                className="font-mono"
                autoFocus
              />
            </Form.Item>

            <div className="space-y-1.5 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-2)]/40 p-3 text-xs">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold">
                <DeleteOutlined className="text-[var(--color-fail)]" />
                <span>{t('rum.compliance.scope', '删除范围')}</span>
              </div>
              <p className="leading-relaxed text-[var(--color-text-3)]">
                {t(
                  'rum.compliance.scopeDetail',
                  '全部 RUM 数据：该用户的会话流、错误聚合样本，以及对象存储中的 Session Replay 录屏切片将被永久抹除。',
                )}
              </p>
            </div>
          </Form>
        </div>
      </Drawer>
    </div>
  );
}
