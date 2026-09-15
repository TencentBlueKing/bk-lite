'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const RELATIONSHIPS_PATH = '/cmdb/assetData/detail/relationships';

export default function RelatedTopologyLegacyRedirect() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = searchParams.toString();

  useEffect(() => {
    const params = new URLSearchParams(query);
    params.set('tab', 'topo');
    const next = params.toString();
    router.replace(next ? `${RELATIONSHIPS_PATH}?${next}` : RELATIONSHIPS_PATH);
  }, [query, router]);

  return null;
}
