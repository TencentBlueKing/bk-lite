'use client';

import React, { useEffect } from 'react';
import { message } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { PORTAL_HOME_PATH } from '@/utils/route';

const shownFallbacks = new Set<string>();

/** 登录落地发现仪表盘缺失或当前组织不可见时，轻提示后停在工作台，不改已保存配置。 */
const HomepageFallbackNotice: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fallback = searchParams.get('homepage_fallback');

  useEffect(() => {
    if (fallback !== 'missing' && fallback !== 'org') {
      return;
    }
    if (shownFallbacks.has(fallback)) {
      return;
    }
    shownFallbacks.add(fallback);
    message.warning(
      fallback === 'missing'
        ? t('opsHomepage.fallbackMissing')
        : t('opsHomepage.fallbackOrg'),
    );
    router.replace(PORTAL_HOME_PATH);
  }, [fallback, router, t]);

  return null;
};

export default HomepageFallbackNotice;
