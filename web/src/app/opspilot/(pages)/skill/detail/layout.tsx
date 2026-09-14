'use client';

import React, { useCallback, useMemo } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import WithSideMenuLayout from '@/components/sub-layout';
import type { MenuItem } from '@/types';
import { SkillProvider, useSkill } from '@/app/opspilot/context/skillContext';
import { pickStableIcon } from '@/app/opspilot/utils/pickStableIcon';
import OpsPilotEntityDetailIntro from '@/app/opspilot/components/opspilot-entity-detail-intro';

// 与列表页 SkillCard / EntityCard 保持完全统一的图标池与算法
const SKILL_ICON_POOL = ['jiqirenjiaohukapian', 'jiqiren', 'jiqiren1', 'jiqiren2'];

const LayoutContent = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { skillInfo } = useSkill();

  const id = searchParams?.get('id') || '';
  const queryName = searchParams?.get('name') || '';
  const queryDesc = searchParams?.get('desc') || '';
  const displayName = skillInfo.name || queryName;
  const displayIntro = skillInfo.introduction || queryDesc;

  // 使用与列表页完全一致的稳定 hash 算法（同一个智能体展示相同图标）
  const iconType =
    pickStableIcon(id, SKILL_ICON_POOL, displayName) || 'jiqirenjiaohukapian';

  const handleBackButtonClick = useCallback(() => {
    router.push('/opspilot/skill');
  }, [router]);

  const customMenuItems: MenuItem[] = useMemo(() => {
    const items: MenuItem[] = [
      {
        name: 'skill_setting',
        title: t('skill.settings.menu', '设置'),
        url: '/opspilot/skill/detail/settings',
        icon: 'settings-fill',
        operation: [],
      },
      {
        name: 'skill_channel',
        title: t('skill.channel.menu', '发布'),
        url: '/opspilot/skill/detail/channel',
        icon: 'channel1',
        operation: [],
      },
    ];

    if (pathname?.includes('/rules')) {
      items.push({
        name: 'skill_rules',
        title: t('skill.rules.menu', '规则'),
        url: '/opspilot/skill/detail/rules',
        icon: 'biangengjilu',
        operation: [],
      });
    }

    return items;
  }, [t, pathname]);

  const intro = (
    <OpsPilotEntityDetailIntro
      name={displayName}
      description={displayIntro}
      iconType={iconType}
      fallbackTitle={t('skill.detail.title', '智能体详情')}
      emptyIntroText={t('skill.detail.noIntro', '暂无简介')}
    />
  );

  return (
    <WithSideMenuLayout
      intro={intro}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
      layoutType="sideMenu"
      introLayout="unified"
      customMenuItems={customMenuItems}
    >
      {children}
    </WithSideMenuLayout>
  );
};

const SkillSettingsLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <SkillProvider>
      <LayoutContent>{children}</LayoutContent>
    </SkillProvider>
  );
};

export default SkillSettingsLayout;
