'use client';

import React, { useEffect, useState } from 'react';
import { Spin, message } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { PORTAL_HOME_PATH } from '@/utils/route';
import { OpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';
import { useHomepageApi, type HomepageAccess } from '@/app/ops-analysis/api/homepage';
import type { DirItem } from '@/app/ops-analysis/types';

interface OpsHomepageDashboardProps {
  dashboardId: string;
}

const OpsHomepageDashboard: React.FC<OpsHomepageDashboardProps> = ({ dashboardId }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { loading } = useUserInfoContext();
  const { getAccess } = useHomepageApi();
  const [access, setAccess] = useState<HomepageAccess | null>(null);
  const [accessId, setAccessId] = useState<string | null>(null);
  if (accessId !== dashboardId) {
    setAccessId(dashboardId);
    setAccess(null);
  }

  useEffect(() => {
    if (loading) {
      return;
    }
    let cancelled = false;
    void getAccess(dashboardId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (result.status === 'ok') {
          setAccess(result);
          return;
        }
        if (result.status === 'missing') {
          message.warning(t('opsHomepage.fallbackMissing'));
        } else if (result.status === 'org') {
          message.warning(t('opsHomepage.fallbackOrg'));
        }
        router.replace(PORTAL_HOME_PATH);
      })
      .catch(() => {
        if (!cancelled) {
          router.replace(PORTAL_HOME_PATH);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dashboardId, getAccess, loading, router, t]);

  if (loading || !access) {
    return (
      <div className="flex h-[calc(100vh-90px)] items-center justify-center">
        <Spin />
      </div>
    );
  }

  const selectedDashboard: DirItem = {
    id: `homepage-${dashboardId}`,
    data_id: String(dashboardId),
    name: access.name,
    desc: access.desc,
    type: 'dashboard',
    is_build_in: access.is_build_in,
  };

  return (
    <div className="flex h-[calc(100vh-90px)] min-h-0 w-full flex-col overflow-hidden">
      <OpsAnalysisProvider>
        <Dashboard selectedDashboard={selectedDashboard} homepageMode />
      </OpsAnalysisProvider>
    </div>
  );
};

export default OpsHomepageDashboard;
