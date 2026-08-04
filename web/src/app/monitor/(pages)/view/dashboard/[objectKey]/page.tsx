'use client';

import { useEffect, useState } from 'react';
import { Empty, Spin } from 'antd';
import { useParams } from 'next/navigation';
import type { ComponentType } from 'react';
import { loadDashboardComponent } from '@/app/monitor/dashboards/component-loaders';
import { normalizeDashboardKey } from '@/app/monitor/dashboards/shared/utils';
import { useResolveObjectId } from '@/app/monitor/dashboards/shared/utils/use-resolve-object-id';
import { DashboardLayout } from '@/app/monitor/dashboards/components/dashboard-layout';

export default function ProfessionalDashboardPage() {
  const params = useParams<{ objectKey: string }>();
  const objectKey = normalizeDashboardKey(params?.objectKey);
  const [DashboardComponent, setDashboardComponent] = useState<ComponentType | null>(null);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'missing'>('loading');

  useResolveObjectId(params?.objectKey || '');

  useEffect(() => {
    let active = true;
    setLoadState('loading');
    setDashboardComponent(null);

    loadDashboardComponent(objectKey)
      .then((component) => {
        if (!active) return;
        if (component) {
          setDashboardComponent(() => component);
          setLoadState('ready');
        } else {
          setLoadState('missing');
        }
      })
      .catch(() => {
        if (active) setLoadState('missing');
      });

    return () => {
      active = false;
    };
  }, [objectKey]);

  return (
    <DashboardLayout objectKey={params?.objectKey || ''}>
      {loadState === 'loading' ? (
        <div className="flex justify-center items-center" style={{ minHeight: 240 }}>
          <Spin />
        </div>
      ) : DashboardComponent ? (
        <DashboardComponent />
      ) : (
        <Empty description="未找到对应的专业仪表盘" style={{ margin: '120px auto' }} />
      )}
    </DashboardLayout>
  );
}
