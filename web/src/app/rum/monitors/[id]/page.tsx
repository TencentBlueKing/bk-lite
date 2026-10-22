'use client';

import { useParams } from 'next/navigation';

import MonitorPolicyEditor from '@/app/rum/monitors/ui/monitor-policy-editor';

export default function RumMonitorEditPage() {
  const params = useParams<{ id: string }>();
  const monitorId = params.id || '';
  return <MonitorPolicyEditor monitorId={monitorId} />;
}
