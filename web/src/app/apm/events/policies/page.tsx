'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Input, message, Popconfirm, Space, Switch, Tag, type TableColumnsType } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type { ApmPolicy } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

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
      render: (_, item) => <Link href={`/apm/events/policies/${item.id}`}>{item.name}</Link>,
    },
    {
      title: t('apm.common.service', '服务'),
      render: (_, item) => `${item.service_namespace ? `${item.service_namespace} / ` : ''}${item.service_name}`,
    },
    { title: t('apm.common.environment', '环境'), dataIndex: 'environment' },
    {
      title: t('apm.policies.scope', '端点 / 版本'),
      render: (_, item) => (
        <Space size={[4, 4]} wrap>
          <Tag>{item.endpoints.length ? `${item.endpoints.length} 个端点` : '全部端点'}</Tag>
          <Tag>
            {item.version_mode === 'specific'
              ? `${item.versions.length} 个版本`
              : item.version_mode === 'grouped'
                ? '按版本'
                : '全部版本'}
          </Tag>
        </Space>
      ),
    },
    {
      title: t('apm.policies.condition', '告警条件'),
      render: (_, item) =>
        `${item.metric_type} · ${item.thresholds.map((rule) => `${rule.severity} ${rule.comparator} ${rule.value}`).join(' / ')}`,
    },
    {
      title: t('apm.policies.status', '状态'),
      render: (_, item) =>
        item.state?.status === 'active' ? <Tag color="red">告警中</Tag> : <Tag color="green">正常</Tag>,
    },
    {
      title: t('common.operation', '操作'),
      fixed: 'right',
      width: 220,
      render: (_, item) => (
        <Space>
          <Switch
            checked={item.is_enabled}
            loading={busyId === item.id}
            checkedChildren="启用"
            unCheckedChildren="停用"
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
          <Link href={`/apm/events/policies/${item.id}`}>
            <Button className="!min-h-11 !min-w-11" type="text" icon={<EditOutlined />} aria-label="编辑策略" />
          </Link>
          <Popconfirm
            title="删除策略不会删除历史告警和快照，确认删除？"
            onConfirm={async () => {
              await deletePolicy(item.id);
              message.success('策略已删除，历史证据已保留');
              load();
            }}
          >
            <Button
              className="!min-h-11 !min-w-11"
              danger
              type="text"
              icon={<DeleteOutlined />}
              aria-label="删除策略"
            />
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
    >
      <div className="mb-3 flex justify-end">
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
      </div>
      <ApmSurface>
        <Input.Search
          className="mb-4 max-w-md"
          allowClear
          placeholder="搜索策略、服务、环境或端点"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        {state === 'ready' ? (
          <ApmDataTable
            rowKey="id"
            columns={columns}
            dataSource={visible}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1180 }}
          />
        ) : (
          <CatalogState kind={state} onRetry={load} />
        )}
      </ApmSurface>
    </ApmRouteShell>
  );
}
