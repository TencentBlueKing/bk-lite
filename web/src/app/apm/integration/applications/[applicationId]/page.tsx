'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Descriptions, Space, Tag, Typography, type TableColumnsType } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import ServiceLanguage from '@/app/apm/components/service-language';
import ApmStatusTag from '@/app/apm/components/status-tag';
import type { ApmApplication, ApmService } from '@/app/apm/types';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';

export default function ApmApplicationDetailPage() {
  const { t } = useTranslation();
  const params = useParams<{ applicationId: string }>();
  const { getApplication, getServices, isLoading } = useApmApi();
  const [application, setApplication] = useState<ApmApplication>();
  const [services, setServices] = useState<ApmService[]>([]);
  const [state, setState] = useState<PageState>('loading');

  useEffect(() => {
    if (isLoading || !params.applicationId) return;
    setState('loading');
    Promise.all([getApplication(params.applicationId), getServices()])
      .then(([item, allServices]) => {
        setApplication(item);
        setServices(allServices.filter((service) => service.application_id === item.application_id));
        setState('ready');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [getApplication, getServices, isLoading, params.applicationId]);

  const columns = useMemo<TableColumnsType<ApmService>>(() => [
    {
      title: t('apm.common.service', '服务'),
      render: (_, service) => (
        <Space size={8}>
          <ServiceLanguage language={service.language} />
          <Link
            href={`/apm/services/${service.id}${service.environment_views[0]?.environment ? `?environment=${encodeURIComponent(service.environment_views[0].environment)}` : ''}`}
            className="font-medium text-[var(--color-primary)] hover:underline"
          >
            {service.name}
          </Link>
        </Space>
      ),
    },
    {
      title: t('apm.common.environment', '环境'),
      width: 240,
      responsive: ['sm'],
      render: (_, service) => (
        <div className="flex flex-wrap gap-1">
          {service.environment_views.length
            ? service.environment_views.map((view) => <Tag bordered={false} key={view.environment}>{view.environment || t('apm.common.unset', '未设置')}</Tag>)
            : <Typography.Text type="secondary">—</Typography.Text>}
        </div>
      ),
    },
    { title: t('apm.common.status', '状态'), dataIndex: 'status', width: 100, align: 'center', render: (value) => <ApmStatusTag status={value} /> },
    {
      title: t('apm.instances.lastReport', '最近上报'),
      dataIndex: 'last_seen_at',
      width: 190,
      responsive: ['lg'],
      render: (value) => <EllipsisWithTooltip text={new Date(value).toLocaleString()} />,
    },
  ], [t]);

  return (
    <ApmRouteShell
      title={application?.name ?? t('apm.applications.detailTitle', '应用详情')}
      description={t('apm.applications.detailDescription', '查看应用边界、下属服务并发起新的遥测接入。')}
    >
      {state === 'ready' && application ? (
        <div className="flex flex-col gap-3">
          <div className="flex justify-end gap-2">
            <Link href="/apm/integration/applications"><Button icon={<ArrowLeftOutlined aria-hidden="true" />}>{t('apm.applications.backToList', '返回列表')}</Button></Link>
            <Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}>
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />}>{t('apm.applications.addIngest', '添加接入')}</Button>
            </Link>
          </div>
          <ApmSurface>
            <Descriptions
              column={{ xs: 1, sm: 2, lg: 3 }}
              items={[
                { key: 'id', label: t('apm.applications.id', '应用 ID'), children: <span className="font-mono">{application.application_id}</span> },
                { key: 'services', label: t('apm.applications.serviceCount', '服务数'), children: <span className="tabular-nums">{services.length}</span> },
                { key: 'organizations', label: t('apm.common.organization', '组织'), children: application.organization_ids.length ? application.organization_ids.map((id) => <Tag key={id}>#{id}</Tag>) : '—' },
                { key: 'description', label: t('apm.applications.note', '说明'), span: 3, children: application.description || '—' },
              ]}
            />
          </ApmSurface>
          <ApmSurface>
            <div className="mb-4">
              <Typography.Text strong>{t('apm.applications.childServices', '下属服务')}</Typography.Text>
              <Typography.Text type="secondary" className="ml-2 !text-xs">{t('apm.common.serviceCount', '共 {count} 个', { count: services.length })}</Typography.Text>
            </div>
            {services.length ? (
              <ApmDataTable
                columns={columns}
                dataSource={services}
                rowKey="id"
                pagination={{ defaultPageSize: 20, pageSizeOptions: [10, 20, 50, 100], showSizeChanger: true }}
              />
            ) : (
              <CatalogState
                kind="empty"
                description={t('apm.applications.noServices', '该应用还没有观测到服务。')}
                action={<Link href={`/apm/integration/add?application_id=${encodeURIComponent(application.application_id)}`}><Button type="primary">{t('apm.applications.addIngest', '添加接入')}</Button></Link>}
              />
            )}
          </ApmSurface>
        </div>
      ) : (
        <ApmSurface padding="none">
          <CatalogState kind={state === 'ready' ? 'error' : state} />
        </ApmSurface>
      )}
    </ApmRouteShell>
  );
}
