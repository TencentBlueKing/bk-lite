'use client';
import React, { useState, useEffect } from 'react';
import BottomTabBar from '@/components/bottom-tab-bar';
import LanguageSelector from '@/components/language-selector';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';
import { getLoginInfo } from '@/api/auth';
import { UserLoginInfo } from '@/types/user';
import { List, Avatar, Button, Switch, Toast } from 'antd-mobile';
import {
  RightOutline,
  SetOutline,
  QuestionCircleOutline,
} from 'antd-mobile-icons';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const [userInfo, setUserInfo] = useState<UserLoginInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const { logout, isLoading: authLoading } = useAuth();

  useEffect(() => {
    const fetchUserInfo = async () => {
      try {
        setLoading(true);
        const { data } = await getLoginInfo();
        setUserInfo(data);
      } catch (error) {
        console.error('获取用户信息失败:', error);
        Toast.show({
          content: '获取用户信息失败',
          icon: 'fail',
        });
      } finally {
        setLoading(false);
      }
    };

    fetchUserInfo();
  }, []);

  const handleLogout = async () => {
    try {
      await logout();
      Toast.show({
        content: t('auth.logoutSuccess'),
        icon: 'success',
      });
    } catch (error) {
      console.error('退出登录失败:', error);
      Toast.show({
        content: t('auth.logoutFailed'),
        icon: 'fail',
      });
    }
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
    <div className="flex flex-col h-screen bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
        <h1 className="text-base font-medium text-[var(--color-text-1)]">
          {t('navigation.profile')}
        </h1>
      </div>

      {/* 用户信息卡片 */}
      <div className="mx-4 mt-4 mb-6 p-5 bg-[var(--color-bg)] rounded-2xl shadow-sm">
        <div className="flex items-center">
          <Avatar
            src="/avatars/default.png"
            style={{ '--size': '48px' }}
            className="mr-3"
          />
          <div className="flex-1">
            <h2 className="text-base font-semibold text-[var(--color-text-1)] mb-1">
              {loading
                ? t('common.loading')
                : userInfo?.display_name || userInfo?.username || '用户'}
            </h2>
            {userInfo?.is_superuser && (
              <div className="inline-flex items-center px-2 py-1 bg-gradient-to-r from-yellow-400 to-orange-400 rounded-full">
                <span className="text-white text-xs font-medium">
                  超级管理员
                </span>
              </div>
            )}
            {!userInfo?.is_superuser &&
              userInfo?.roles &&
              userInfo.roles.length > 0 && (
              <div className="inline-flex items-center px-2 py-1 bg-gradient-to-r from-blue-400 to-purple-400 rounded-full">
                <span className="text-white text-xs font-medium">
                  {userInfo.roles[0]}
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
                      className: 'text-[var(--color-primary)] text-base',
                    })}
                  </div>
                }
                onClick={item.onClick}
                clickable
              >
                <span className="text-[var(--color-text-1)] text-sm font-medium">
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
              <span className="text-[var(--color-text-1)] text-sm font-medium">
                {t('common.darkMode')}
              </span>
            </List.Item>
          </List>
        </div>

        {/* 退出登录按钮 */}
        <div className="mx-4 mt-6">
          <Button
            block
            size="small"
            color="danger"
            fill="outline"
            className="rounded-md text-xs"
            loading={authLoading}
            onClick={handleLogout}
            style={
              {
                '--border-radius': '0.375rem',
                height: '36px',
                fontSize: '12px',
              } as React.CSSProperties
            }
          >
            {authLoading ? t('common.loggingOut') : t('common.logout')}
          </Button>
        </div>
      </div>

      {/* 底部导航 */}
      <BottomTabBar />
    </div>
  );
}
