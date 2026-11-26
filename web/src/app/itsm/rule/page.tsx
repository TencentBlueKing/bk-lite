'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function RulePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/itsm/rule/status');
  }, [router]);
  return null;
}
