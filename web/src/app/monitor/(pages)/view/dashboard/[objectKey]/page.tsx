'use client';

import { Empty } from 'antd';
import { useParams } from 'next/navigation';
import { PROFESSIONAL_DASHBOARD_MAP } from '@/app/monitor/dashboards/registry';
import { normalizeDashboardKey } from '@/app/monitor/dashboards/utils';

export default function ProfessionalDashboardPage() {
  const params = useParams<{ objectKey: string }>();
  const objectKey = normalizeDashboardKey(params?.objectKey);
  const DashboardComponent = PROFESSIONAL_DASHBOARD_MAP.get(objectKey);

  if (!DashboardComponent) {
    return <Empty description="未找到对应的专业仪表盘" style={{ margin: '120px auto' }} />;
  }

  return <DashboardComponent />;
}
