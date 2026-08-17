'use client';

import { useParams } from 'next/navigation';
import ApmPolicyEditor from '@/app/apm/events/policies/policy-editor';

export default function ApmPolicyEditPage() {
  const params = useParams<{ policyId: string }>();
  return <ApmPolicyEditor policyId={params.policyId} />;
}
