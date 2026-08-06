'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Dialog, List, Switch, Toast } from 'antd-mobile';
import LanguageSelector from '@/components/language-selector';
import MobileTabShell from '@/components/mobile-tab-shell';
import MobilePageHeader from '@/components/mobile-page-header';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useTranslation } from '@/utils/i18n';
import { useMobileAvailability } from '@/platform/availability/context';
import { getUserInfo, type AccountUserInfo } from '@/api/user';
import styles from './page.module.css';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const { userInfo, logout, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const { status: availabilityStatus, refresh: refreshAvailability } = useMobileAvailability();
  const [account, setAccount] = useState<AccountUserInfo | null>(null);
  const [accountStatus, setAccountStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  const loadAccount = useCallback(async () => {
    setAccountStatus('loading');
    try {
      const response = await getUserInfo();
      if (!response.result) throw new Error(response.message || 'Unable to load account');
      setAccount(response.data);
      setAccountStatus('ready');
    } catch {
      setAccountStatus('error');
    }
  }, []);

  useEffect(() => { void loadAccount(); }, [loadAccount]);

  const organizations = useMemo(() => (
    (account?.group_list || []).map((item) => item.name).filter((name): name is string => Boolean(name))
  ), [account?.group_list]);
  const roles = useMemo(() => {
    const values = (account?.role_list || []).map((role) => {
      if (!role.app && role.name === 'admin') return t('account.superAdmin');
      return role.app_display_name ? `${role.app_display_name} · ${role.name}` : role.name;
    }).filter(Boolean);
    return Array.from(new Set(values));
  }, [account?.role_list, t]);
  const displayName = account?.display_name || userInfo?.display_name || userInfo?.username || t('account.user');
  const username = account?.username || userInfo?.username || '--';
  const domain = account?.domain || userInfo?.domain || '--';

  const handleLogoutClick = () => {
    void Dialog.confirm({
      content: t('auth.logoutConfirm'),
      confirmText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          await logout();
        } catch {
          Toast.show({ content: t('auth.logoutFailed'), icon: 'fail' });
        }
      },
    });
  };

  return (
    <MobileTabShell activeTab="profile">
      <main className={styles.page}>
        <MobilePageHeader title={t('navigation.profile')} />
        <div className={styles.scroll}>
          <section className={styles.identity} aria-label={t('account.title')}>
            <div className={styles.avatar} aria-hidden="true">{displayName.charAt(0).toUpperCase() || 'U'}</div>
            <div className={styles.identityCopy}>
              <h2>{displayName}</h2>
              <p>@{username}</p>
              {accountStatus === 'ready' && (organizations.length > 0 || roles.length > 0) && (
                <div className={styles.identityMeta} aria-label={t('account.accountOverview')}>
                  {organizations.map((name) => (
                    <span className={styles.metaChip} key={`org-${name}`}>
                      {t('account.organization')} · {name}
                    </span>
                  ))}
                  {roles.map((name) => (
                    <span className={styles.metaChip} key={`role-${name}`}>
                      {name}
                    </span>
                  ))}
                </div>
              )}
              {accountStatus === 'loading' && (
                <div className={styles.identityMetaLoading} role="status" aria-label={t('common.loading')}>
                  <span /><span />
                </div>
              )}
            </div>
            <span className={styles.domain}>{domain}</span>
          </section>

          {accountStatus === 'error' && (
            <div className={styles.inlineNotice} role="alert">
              <span>{t('account.loadFailed')}</span>
              <button type="button" onClick={() => void loadAccount()}>{t('common.retry')}</button>
            </div>
          )}

          {availabilityStatus === 'error' && (
            <div className={styles.inlineNotice} role="alert">
              <span>{t('availability.loadFailed')}</span>
              <button type="button" onClick={() => void refreshAvailability()}>{t('common.retry')}</button>
            </div>
          )}

          <section className={styles.menuSection}>
            <List>
              <List.Item
                prefix={<span className={`${styles.menuIcon} iconfont icon-zhanghaoyuanquan`} aria-hidden="true" />}
                onClick={() => router.push('/profile/accountDetails')}
                clickable
              >
                {t('common.accountsAndSecurity')}
              </List.Item>
            </List>
          </section>

          <section className={styles.menuSection}>
            <List>
              <LanguageSelector />
              <List.Item
                prefix={<span className={`${styles.menuIcon} iconfont icon-yueliang`} aria-hidden="true" />}
                extra={<Switch checked={isDark} onChange={toggleTheme} style={{ '--height': '28px', '--width': '48px' }} />}
              >
                {t('common.darkMode')}
              </List.Item>
            </List>
          </section>

          <button type="button" className={styles.logoutButton} disabled={authLoading} onClick={handleLogoutClick}>
            {authLoading ? t('common.loggingOut') : t('common.logout')}
          </button>
        </div>
      </main>
    </MobileTabShell>
  );
}
