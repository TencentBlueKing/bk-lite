'use client';

import { useParams } from 'next/navigation';
import ApplicationObservability from '@/app/apm/components/application-observability';

export default function ApmServiceApplicationDetailPage() {
  const params = useParams<{ applicationId: string }>();
  return <ApplicationObservability applicationId={params.applicationId} />;
}
