'use client';

import React from 'react';
import Link from 'next/link';
import { Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useEffectiveHomepage } from '@/app/ops-analysis/context/effectiveHomepage';
import { effectiveHomepageHref } from '@/app/ops-analysis/utils/homepageLanding';

interface HomepageBrandLinkProps {
  children: React.ReactNode;
}

/** 顶栏 Logo 与产品名：同一标签打开有效首页，悬停后提示可返回。 */
const HomepageBrandLink: React.FC<HomepageBrandLinkProps> = ({ children }) => {
  const { t } = useTranslation();
  const { entry } = useEffectiveHomepage();

  return (
    <Tooltip title={t('opsHomepage.backToHomepage')}>
      <Link
        href={effectiveHomepageHref(entry)}
        prefetch={false}
        data-testid="portal-brand-link"
        className="flex min-w-0 cursor-pointer items-center space-x-2 text-inherit transition-opacity hover:text-inherit hover:opacity-80"
      >
        {children}
      </Link>
    </Tooltip>
  );
};

export default HomepageBrandLink;
