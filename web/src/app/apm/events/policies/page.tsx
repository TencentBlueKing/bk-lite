'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Avatar, Button, message, Popconfirm, Space, Switch, Typography, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatDateTime } from '@/app/apm/components/metric-format';
import type { ApmPolicy } from '@/app/apm/types';
import SearchActionBar from '@/components/search-action-bar';
import { useTranslation } from '@/utils/i18n';
import styles from '@/app/apm/events/event-workspace.module.scss';

type PageState = CatalogStateKind | 'ready';

function formatExecutionTime(policy: ApmPolicy, evaluationFailed: (time: string) => string) {
  const failedAt = policy.state?.last_failed_at;
  const succeededAt = policy.state?.last_succeeded_at;
  const failed = failedAt && (!succeededAt || dayjs(failedAt).isAfter(succeededAt));
  if (failed) {
    return { label: evaluationFailed(formatDateTime(failedAt, false)), failed: true };
  }
  return { label: formatDateTime(succeededAt, false), failed: false };
}

export default function ApmPolicyListPage() {
  const { t } = useTranslation();
  const { deletePolicy, getPolicies, isLoading: authLoading, setPolicyEnabled } = useApmApi();
  const [items, setItems] = useState<ApmPolicy[]>([]);
  const [state, setState] = useState<PageState>('loading');
  const [keyword, setKeyword] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    getPolicies()
      .then((policies) => {
        setItems(policies);
        setState(policies.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, getPolicies]);

  useEffect(() => load(), [load]);

  const visible = useMemo(() => {
    const value = keyword.trim().toLocaleLowerCase();
    if (!value) return items;
    return items.filter((item) =>
      [item.name, item.service_name, item.environment, ...item.endpoints].some((part) =>
        part.toLocaleLowerCase().includes(value),
      ),
    );
  }, [items, keyword]);

  const columns: TableColumnsType<ApmPolicy> = [
    {
      title: t('apm.policies.name', '策略名称'),
      dataIndex: 'name',
      render: (_, item) => (
        <Link className={styles.policyNameLink} href={`/apm/events/policies/${item.id}`} title={item.name}>
          {item.name}
        </Link>
      ),
    },
    {
      title: t('apm.common.service', '服务'),
      render: (_, item) => (
        <div className={styles.policyServiceCell}>
          <Typography.Text className={styles.policyServiceName} title={item.service_name}>
            {item.service_name}
          </Typography.Text>
          <Typography.Text type="secondary" className={styles.policyServiceScope} title={item.endpoints.join(', ')}>
            {item.endpoints.length === 0
              ? t('apm.alerts.allEndpoints', '全部端点')
              : item.endpoints.length === 1
                ? item.endpoints[0]
                : t('apm.policies.endpointCount', '{count} 个端点', { count: item.endpoints.length })}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('apm.policies.creatorColumn', '创建人'),
      dataIndex: 'created_by',
      width: APM_TABLE_COLUMN_WIDTHS.organization,
      render: (value: string) => {
        const creator = value?.trim() || t('apm.policies.system', '系统');
        return (
          <Space size={8} className={styles.policyCreatorCell}>
            <Avatar size={28}>{creator.slice(0, 1).toUpperCase()}</Avatar>
            <Typography.Text ellipsis={{ tooltip: creator }}>{creator}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: t('apm.policies.createdAt', '创建时间'),
      dataIndex: 'created_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (value: string) => (
        <span className={styles.policyTimeCell}>
          <ClockCircleOutlined aria-hidden="true" />
          {formatDateTime(value, false)}
        </span>
      ),
    },
    {
      title: t('apm.policies.executionTime', '执行时间'),
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (_, item) => {
        const execution = formatExecutionTime(item, (time) => t('apm.policies.evaluationFailed', '评估失败 {time}', { time }));
        return (
          <span className={styles.policyTimeCell}>
            <ClockCircleOutlined aria-hidden="true" />
            <Typography.Text type={execution.failed ? 'warning' : undefined}>
              {execution.label}
            </Typography.Text>
          </span>
        );
      },
    },
    {
      title: t('apm.policies.enablement', '启停'),
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (_, item) => (
        <Switch
          size="small"
          checked={item.is_enabled}
          loading={busyId === item.id}
          aria-label={t(item.is_enabled ? 'apm.policies.disableNamed' : 'apm.policies.enableNamed', item.is_enabled ? '停用策略 {name}' : '启用策略 {name}', { name: item.name })}
          onChange={async (enabled) => {
            setBusyId(item.id);
            try {
              const updated = await setPolicyEnabled(item.id, enabled);
              setItems((current) => current.map((policy) => (policy.id === item.id ? updated : policy)));
            } finally {
              setBusyId(null);
            }
          }}
        />
      ),
    },
    {
      title: t('apm.common.operation', '操作'),
      fixed: 'right',
      width: APM_TABLE_COLUMN_WIDTHS.actionPair,
      render: (_, item) => (
        <Space size={0} className={styles.policyOperationCell}>
          <Link href={`/apm/events/policies/${item.id}`}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('apm.policies.editNamed', '编辑策略 {name}', { name: item.name })}
            >
              {t('common.edit', '编辑')}
            </Button>
          </Link>
          <Popconfirm
            title={t('apm.policies.deleteEvidenceConfirm', '删除策略不会删除历史告警和快照，确认删除？')}
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              await deletePolicy(item.id);
              message.success(t('apm.policies.deletedEvidenceKept', '策略已删除，历史证据已保留'));
              load();
            }}
          >
            <Button
              danger
              type="link"
              size="small"
              icon={<DeleteOutlined />}
              aria-label={t('apm.policies.deleteNamed', '删除策略 {name}', { name: item.name })}
            >
              {t('common.delete', '删除')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.policies.title', '告警策略')}
      description={t('apm.policies.listDescription', '面向 APM Service、端点、环境和版本的独立策略。启停只在列表执行。')}
      dependency="control"
    >
      <ApmSurface>
        <div className="flex flex-col gap-4">
        <SearchActionBar
          spacing="flush"
          className={styles.policyToolbar}
          searchClassName="!w-80"
          searchProps={{
            placeholder: t('apm.policies.searchPlaceholder', '搜索策略、服务、环境或端点'),
            value: keyword,
            onChange: (event) => setKeyword(event.target.value),
            onSearch: (value) => setKeyword(value.trim()),
          }}
          actions={(
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>
                {t('apm.common.refresh', '刷新')}
              </Button>
              <Link href="/apm/events/policies/new">
                <Button type="primary" icon={<PlusOutlined />}>
                  {t('apm.policies.new', '新建策略')}
                </Button>
              </Link>
            </Space>
          )}
        />
        {state === 'ready' ? (
          <ApmDataTable
            rowKey="id"
            columns={columns}
            dataSource={visible}
            locale={{ emptyText: t('apm.policies.noMatching', '没有匹配的策略，请调整搜索条件。') }}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1160 }}
          />
        ) : (
          <CatalogState
            kind={state}
            description={t('apm.policies.empty', '暂无告警策略')}
            onRetry={state === 'empty' ? undefined : load}
          />
        )}
        </div>
      </ApmSurface>
    </ApmRouteShell>
  );
}
