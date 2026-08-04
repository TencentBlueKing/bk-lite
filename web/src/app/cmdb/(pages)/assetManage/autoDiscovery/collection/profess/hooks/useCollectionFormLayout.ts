'use client';

import { useLocale } from '@/context/locale';

export const useCollectionFormLayout = () => {
  const { locale } = useLocale();

  return {
    layout: 'horizontal' as const,
    labelCol: { span: locale === 'en' ? 6 : 5 },
  };
};
