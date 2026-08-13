'use client';
import React from 'react';
import { useTranslation } from '@/utils/i18n';
import PageStatus from '@/components/page-status';

const NotFoundPage = () => {
  const { t } = useTranslation();
  return (
    <PageStatus
      code="404"
      title={t('common.notFound')}
      actionHref="/"
      actionLabel={t('common.backToHome')}
      imageAlt="404 Not Found"
    />
  );
};

export default NotFoundPage;
