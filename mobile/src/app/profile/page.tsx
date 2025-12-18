'use client';
import { useRouter } from 'next/navigation';
import LanguageSelector from '@/components/language-selector';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';
import { List, Switch, Toast, Dialog } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const { userInfo, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();


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

  return (
    <div className="flex flex-col h-full bg-[var(--color-background-body)]">
      {/* 顶部导航栏 */}
      <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
        <button onClick={() => router.back()} className="absolute left-4">
          <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
        </button>
        <h1 className="text-lg font-medium text-[var(--color-text-1)]">
          {t('navigation.profile')}
        </h1>
      </div>

      {/* 用户信息卡片 */}
      <div className="mx-4 mt-4 mb-6 p-5 bg-[var(--color-bg)] rounded-2xl shadow-sm">
        <div className="flex items-center">
          <div
            className="flex items-center justify-center flex-shrink-0 rounded-full mr-3 text-2xl font-semibold text-white bg-[var(--color-primary)]"
            style={{
              width: '50px',
              height: '50px',
            }}
          >
            {userInfo?.display_name?.charAt(0)?.toUpperCase() || userInfo?.username?.charAt(0)?.toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-[var(--color-text-1)] mb-1 truncate">
              {userInfo?.display_name || userInfo?.username || t('account.user')}
            </h2>
            <span className="text-[var(--color-text-3)] text-xs font-medium truncate block">
              {t('account.username')}:{userInfo?.username}
            </span>
          </div>
          {userInfo?.domain && (
            <div className="inline-flex items-center px-2 py-0.5 bg-blue-500 rounded">
              <span className="text-white text-xs font-medium">
                {userInfo.domain}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 功能菜单 */}
      <div className="flex-1">
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            <List.Item
              prefix={
                <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                  <span className="iconfont icon-zhanghaoyuanquan text-[var(--color-primary)] text-lg"></span>
                </div>
              }
              onClick={() => {
                router.push('/profile/accountDetails');
              }}
              clickable
            >
              <span className="text-[var(--color-text-1)] text-base font-medium">
                {t('common.accountsAndSecurity')}
              </span>
            </List.Item>
          </List>
        </div>

        {/* 设置选项 */}
        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
          <List>
            <LanguageSelector />
            <List.Item
              prefix={
                <div className="flex items-center justify-center w-7 h-7 bg-[var(--color-primary-bg-active)] rounded-lg mr-2.5">
                  <span className="iconfont icon-yueliang text-yellow-500 text-lg"></span>
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
    </div>
  );
}
