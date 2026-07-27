'use client';

import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';

export interface NodeManagerDetailSummary {
  name: string;
  introduction: string;
  icon: string;
}

const useDetailSummary = (
  fallbackIcon = 'caijiqizongshu',
): NodeManagerDetailSummary => {
  const searchParams = useSearchParams();
  const name = searchParams.get('displayName') || '';
  const introduction = searchParams.get('introduction') || '';
  const icon = searchParams.get('icon') || fallbackIcon;

  return useMemo(
    () => ({
      name,
      introduction,
      icon,
    }),
    [fallbackIcon, icon, introduction, name],
  );
};

export default useDetailSummary;
