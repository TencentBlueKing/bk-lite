'use client';
import React from 'react';
import { useTranslation } from '@/utils/i18n';
import PageStatus from '@/components/page-status';

const NotPermissionPage = () => {
  const { t } = useTranslation();
  return (
    <PageStatus
      code="403"
      title={t('common.noPermission')}
      actionHref="/"
      actionLabel={t('common.backToHome')}
      imageAlt="403 No Permission"
    />
  );
};

export default NotPermissionPage;
