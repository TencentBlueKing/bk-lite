'use client';
import React, { useState } from 'react';
import { TabBar } from 'antd-mobile';
import { useRouter, usePathname } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import {
  MessageOutline,
  MessageFill,
  UserOutline,
  UserSetOutline,
} from 'antd-mobile-icons';

export default function BottomTabBar() {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();

  const tabs = [
    {
      key: '/conversations',
      title: t('navigation.conversations'),
      icon: <MessageOutline />,
      activeIcon: <MessageFill />,
    },
    {
      key: '/profile',
      title: t('navigation.profile'),
      icon: <UserOutline />,
      activeIcon: <UserSetOutline />,
    },
  ];

  // 根据当前路径确定活跃的tab
  const getActiveKey = () => {
    if (pathname?.includes('/profile')) return '/profile';
    return '/conversations';
  };

  const [activeKey, setActiveKey] = useState(getActiveKey());

  const handleTabChange = (key: string) => {
    setActiveKey(key);
    router.push(key);
  };

  return (
    <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] tab-bar-container">
      <style
        dangerouslySetInnerHTML={{
          __html: `
          .tab-bar-container .adm-tab-bar-item-title {
            font-weight: 500 !important;
          }
        `,
        }}
      />
      <TabBar
        activeKey={activeKey}
        onChange={handleTabChange}
        style={
          {
            '--adm-font-size-7': '13px',
            '--adm-color-text-secondary': 'var(--color-text-2)',
          } as React.CSSProperties
        }
      >
        {tabs.map((item) => (
          <TabBar.Item
            key={item.key}
            icon={(active) => (active ? item.activeIcon : item.icon)}
            title={item.title}
          />
        ))}
      </TabBar>
    </div>
  );
}
