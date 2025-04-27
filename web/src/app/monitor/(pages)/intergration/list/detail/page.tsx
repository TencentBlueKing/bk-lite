'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function IntergrationDetialPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    const targetUrl = `/monitor/intergration/list/detail/configure?${params.toString()}`;
    router.push(targetUrl);
  }, [router, searchParams]);

  return null;
}
