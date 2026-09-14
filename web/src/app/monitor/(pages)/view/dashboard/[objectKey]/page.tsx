'use client';

import '../register-dashboard-pilot';
import { useEffect, useState } from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useParams } from 'next/navigation';
import type { ComponentType } from 'react';
import { loadDashboardComponent } from '@/app/monitor/dashboards/component-loaders';
import { normalizeDashboardKey } from '@/app/monitor/dashboards/shared/utils';
import { useResolveObjectId } from '@/app/monitor/dashboards/shared/utils/use-resolve-object-id';

export default function ProfessionalDashboardPage() {
  const params = useParams<{ objectKey: string }>();
  const objectKey = normalizeDashboardKey(params?.objectKey);
  const [DashboardComponent, setDashboardComponent] = useState<ComponentType | null>(null);
  const [loadedObjectKey, setLoadedObjectKey] = useState<string>('');
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'missing'>('loading');

  useResolveObjectId(params?.objectKey || '');

  useEffect(() => {
    let active = true;
    setLoadState('loading');

    loadDashboardComponent(objectKey)
      .then((component) => {
        if (!active) return;
        if (component) {
          setDashboardComponent(() => component);
          setLoadedObjectKey(objectKey);
          setLoadState('ready');
        } else {
          setDashboardComponent(null);
          setLoadedObjectKey('');
          setLoadState('missing');
        }
      })
      .catch(() => {
        if (!active) return;
        setDashboardComponent(null);
        setLoadedObjectKey('');
        setLoadState('missing');
      });

    return () => {
      active = false;
    };
  }, [objectKey]);

  if (DashboardComponent && loadedObjectKey === objectKey) {
    return <DashboardComponent key={loadedObjectKey} />;
  }

  if (loadState === 'loading') {
    return (
      <div className="flex min-h-[240px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  return (
    <CompactEmptyState
      description="未找到对应的专业仪表盘"
      className="mx-auto my-[120px]"
    />
  );
}
