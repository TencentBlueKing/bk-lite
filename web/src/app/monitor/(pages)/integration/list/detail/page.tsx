'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function IntegrationDetialPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    const targetUrl = `/monitor/integration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  }, [router, searchParams]);

  return null;
}
