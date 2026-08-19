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
import ApmRouteShell from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmPolicy } from '@/app/apm/types';
import SearchActionBar from '@/components/search-action-bar';
import { useTranslation } from '@/utils/i18n';
import styles from '@/app/apm/events/event-workspace.module.scss';

type PageState = CatalogStateKind | 'ready';

function formatDateTime(value: string | null | undefined) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '--';
}

function getLatestExecutionAt(policy: ApmPolicy) {
  return [policy.state?.last_succeeded_at, policy.state?.last_failed_at]
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => dayjs(right).valueOf() - dayjs(left).valueOf())[0];
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
              ? '全部端点'
              : item.endpoints.length === 1
                ? item.endpoints[0]
                : `${item.endpoints.length} 个端点`}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('apm.common.createdBy', '创建人'),
      dataIndex: 'created_by',
      width: APM_TABLE_COLUMN_WIDTHS.organization,
      render: (value: string) => {
        const creator = value?.trim() || '系统';
        return (
          <Space size={8} className={styles.policyCreatorCell}>
            <Avatar size={28}>{creator.slice(0, 1).toUpperCase()}</Avatar>
            <Typography.Text ellipsis={{ tooltip: creator }}>{creator}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: t('apm.common.createdAt', '创建时间'),
      dataIndex: 'created_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (value: string) => (
        <span className={styles.policyTimeCell}>
          <ClockCircleOutlined aria-hidden="true" />
          {formatDateTime(value)}
        </span>
      ),
    },
    {
      title: t('apm.policies.executionTime', '执行时间'),
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      render: (_, item) => (
        <span className={styles.policyTimeCell}>
          <ClockCircleOutlined aria-hidden="true" />
          {formatDateTime(getLatestExecutionAt(item))}
        </span>
      ),
    },
    {
      title: '启停',
      width: APM_TABLE_COLUMN_WIDTHS.status,
      render: (_, item) => (
        <Switch
          size="small"
          checked={item.is_enabled}
          loading={busyId === item.id}
          aria-label={`${item.name}：${item.is_enabled ? '停用策略' : '启用策略'}`}
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
              aria-label={`${item.name}：编辑策略`}
            >
              编辑
            </Button>
          </Link>
          <Popconfirm
            title="删除策略不会删除历史告警和快照，确认删除？"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              await deletePolicy(item.id);
              message.success('策略已删除，历史证据已保留');
              load();
            }}
          >
            <Button
              danger
              type="link"
              size="small"
              icon={<DeleteOutlined />}
              aria-label={`${item.name}：删除策略`}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.policies.title', '告警策略')}
      description="面向 APM Service、端点、环境和版本的独立策略。启停只在列表执行。"
      dependency="control"
      spacing="flush"
    >
      <section className={styles.policySection} aria-label="告警策略列表">
        <SearchActionBar
          spacing="flush"
          className={styles.policyToolbar}
          searchClassName="!w-80"
          searchProps={{
            placeholder: '搜索策略、服务、环境或端点',
            value: keyword,
            onChange: (event) => setKeyword(event.target.value),
            onSearch: (value) => setKeyword(value.trim()),
          }}
          actions={(
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>
                刷新
              </Button>
              <Link href="/apm/events/policies/new">
                <Button type="primary" icon={<PlusOutlined />}>
                  新建策略
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
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1160, y: 'calc(100vh - 336px)' }}
          />
        ) : (
          <CatalogState kind={state} onRetry={load} />
        )}
      </section>
    </ApmRouteShell>
  );
}
