'use client';

import React from 'react';
import { Button, message } from 'antd';
import { ExportOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';
import { useHomepageApi } from '@/app/ops-analysis/api/homepage';
import { useEffectiveHomepage } from '@/app/ops-analysis/context/effectiveHomepage';
import { buildOpsAnalysisViewHref } from '@/app/ops-analysis/utils/viewHref';
import { effectiveHomepageHref } from '@/app/ops-analysis/utils/homepageLanding';

interface HomepageViewToolbarProps {
  dashboardId?: string;
}

const HomepageViewToolbar: React.FC<HomepageViewToolbarProps> = ({ dashboardId }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { applyPersonal } = useHomepageApi();
  const { refresh: refreshEffectiveHomepage } = useEffectiveHomepage();

  if (!dashboardId) {
    return null;
  }

  const pinWorkbench = async () => {
    try {
      await applyPersonal({ action: 'pin_workbench' });
      message.success(t('opsHomepage.pinWorkbenchSuccess'));
      await refreshEffectiveHomepage();
      // 用户在首页上选择工作台，意图是立即离开仪表盘首页。
      router.replace(effectiveHomepageHref(null));
    } catch {
      // 请求层已经提示失败，停留在当前仪表盘首页。
    }
  };

  return (
    <>
      <Button
        type="link"
        icon={<ExportOutlined />}
        href={buildOpsAnalysisViewHref('dashboard', `dashboard_${dashboardId}`)}
      >
        {t('opsHomepage.openInAnalysis')}
      </Button>
      <MoreActionsDropdown
        ariaLabel={t('opsHomepage.moreActions')}
        items={[
          {
            key: 'pin-workbench',
            label: t('opsHomepage.pinWorkbench'),
            onClick: () => {
              void pinWorkbench();
            },
          },
        ]}
      />
    </>
  );
};

export default HomepageViewToolbar;
