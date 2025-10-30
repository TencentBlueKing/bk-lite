'use client';
import React from 'react';
import BottomTabBar from '@/components/bottom-tab-bar';
import LanguageSelector from '@/components/language-selector';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';
import { List, Avatar, Switch, Toast, Dialog } from 'antd-mobile';
import {
  RightOutline,
  SetOutline,
  QuestionCircleOutline,
} from 'antd-mobile-icons';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const { userInfo, logout, isLoading: authLoading } = useAuth();

  const handleLogoutClick = () => {
    Dialog.confirm({
      content: t('auth.logoutConfirm'),
      confirmText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          await logout();
        } catch (error) {
          console.error('退出登录失败:', error);
          Toast.show({
            content: t('auth.logoutFailed'),
            icon: 'fail',
          });
        }
      },
    });
  };

  const menuItems = [
    {
      title: t('common.helpAndFeedback'),
      icon: <QuestionCircleOutline />,
      onClick: () => console.log('帮助与反馈'),
    },
    {
      title: t('common.settings'),
      icon: <SetOutline />,
      onClick: () => console.log('设置'),
    },
  ];

  return (
    <div className="flex flex-col h-full bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
        <h1 className="text-lg font-medium text-[var(--color-text-1)]">
          {t('navigation.profile')}
        </h1>
      </div>

      {/* 用户信息卡片 */}
      <div className="mx-4 mt-4 mb-6 p-5 bg-[var(--color-bg)] rounded-2xl shadow-sm">
        <div className="flex items-center">
          <Avatar
            src="/avatars/default.png"
            style={{ '--size': '56px' }}
            className="mr-3"
          />
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-[var(--color-text-1)] mb-1">
              {userInfo?.display_name || userInfo?.username || '用户'}
            </h2>
            {userInfo?.domain && (
              <div className="inline-flex items-center px-2 py-0.5 bg-blue-500 rounded">
                <span className="text-white text-xs font-medium">
                  {userInfo.domain}
                </span>
              </div>
            )}
          </div>
          <RightOutline className="text-[var(--color-text-4)]" />
        </div>
      </div>

      {/* 功能菜单 */}
      <div className="flex-1">
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            {menuItems.map((item, index) => (
              <List.Item
                key={index}
                prefix={
                  <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                    {React.cloneElement(item.icon, {
                      className: 'text-[var(--color-primary)] text-lg',
                    })}
                  </div>
                }
                onClick={item.onClick}
                clickable
              >
                <span className="text-[var(--color-text-1)] text-base font-medium">
                  {item.title}
                </span>
              </List.Item>
            ))}
          </List>
        </div>

        {/* 设置选项 */}
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            <LanguageSelector />
            <List.Item
              prefix={
                <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                  <span className="text-[var(--color-primary)] text-base">
                    🌙
                  </span>
                </div>
              }
              extra={
                <Switch
                  checked={isDark}
                  onChange={toggleTheme}
                  style={{
                    '--height': '22px',
                    '--width': '40px',
                  }}
                />
              }
            >
              <span className="text-[var(--color-text-1)] text-base font-medium">
                {t('common.darkMode')}
              </span>
            </List.Item>
          </List>
        </div>

        {/* 退出登录按钮 */}
        <div className="mx-4 mt-6 mb-4">
          <div
            className="bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden cursor-pointer active:opacity-70"
            onClick={authLoading ? undefined : handleLogoutClick}
          >
            <div className="py-2.5 text-center">
              <span
                className={`text-base font-medium ${authLoading ? 'text-[var(--color-text-3)]' : 'text-red-500'
                  }`}
              >
                {authLoading ? t('common.loggingOut') : t('common.logout')}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 底部导航 */}
      <BottomTabBar />
    </div>
  );
}
