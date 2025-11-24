'use client';
import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';

const useCloudId = () => {
  const searchParams = useSearchParams();
  const id = searchParams.get('cloud_region_id');
  return useMemo(() => {
    if (id && typeof id === 'string') {
      return Number(id);
    }
    return 1;
  }, [id]);
};

export default useCloudId;
