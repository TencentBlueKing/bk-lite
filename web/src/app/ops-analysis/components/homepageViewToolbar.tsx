'use client';

import React from 'react';
import { Button } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { buildOpsAnalysisViewHref } from '@/app/ops-analysis/utils/viewHref';

interface HomepageViewToolbarProps {
  dashboardId?: string;
}

const HomepageViewToolbar: React.FC<HomepageViewToolbarProps> = ({ dashboardId }) => {
  const { t } = useTranslation();

  if (!dashboardId) {
    return null;
  }

  return (
    <Button
      type="link"
      icon={<ExportOutlined />}
      href={buildOpsAnalysisViewHref('dashboard', `dashboard_${dashboardId}`)}
    >
      {t('opsHomepage.openInAnalysis')}
    </Button>
  );
};

export default HomepageViewToolbar;
