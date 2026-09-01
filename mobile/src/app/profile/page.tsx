'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Dialog, List, Switch, Toast } from 'antd-mobile';
import { RedoOutline } from 'antd-mobile-icons';
import LanguageSelector from '@/components/language-selector';
import OrganizationSwitcher from '@/components/organization-switcher';
import MobileSafeHeader from '@/components/mobile-safe-header';
import MobileTabShell from '@/components/mobile-tab-shell';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/context/theme';
import { useMobileAvailability } from '@/platform/availability/context';
import { useTranslation } from '@/utils/i18n';
import { getUserInfo, type AccountUserInfo } from '@/api/user';
import {
  readCachedAccountOverview,
  writeCachedAccountOverview,
} from '@/utils/accountOverviewCache';
import styles from './page.module.css';

export default function ProfilePage() {
  const { t } = useTranslation();
  const { toggleTheme, isDark } = useTheme();
  const { userInfo, logout, isLoading: authLoading } = useAuth();
  const { status: availabilityStatus, refresh: refreshAvailability } = useMobileAvailability();
  const router = useRouter();
  const userId = userInfo?.id != null ? String(userInfo.id) : undefined;
  const initialAccount = readCachedAccountOverview(userId);
  const [account, setAccount] = useState<AccountUserInfo | null>(initialAccount);
  const [accountStatus, setAccountStatus] = useState<'loading' | 'ready' | 'error'>(
    initialAccount ? 'ready' : 'loading',
  );
  const [accountRetrying, setAccountRetrying] = useState(false);
  const availabilityAutoRetriedRef = useRef(false);

  const loadAccount = useCallback(async () => {
    const hasCache = Boolean(readCachedAccountOverview(userId));
    if (!hasCache) setAccountStatus('loading');
    try {
      const response = await getUserInfo();
      if (!response.result) throw new Error(response.message || 'Unable to load account');
      writeCachedAccountOverview(userId, response.data);
      setAccount(response.data);
      setAccountStatus('ready');
    } catch {
      if (!readCachedAccountOverview(userId)) setAccountStatus('error');
    }
  }, [userId]);

  const handleAccountRetry = useCallback(async () => {
    setAccountRetrying(true);
    try {
      await loadAccount();
    } finally {
      setAccountRetrying(false);
    }
  }, [loadAccount]);

  useEffect(() => { void loadAccount(); }, [loadAccount]);

  useEffect(() => {
    if (availabilityStatus === 'ready') {
      availabilityAutoRetriedRef.current = false;
      return;
    }
    // One automatic retry when Me becomes the fail-closed landing surface; avoid error→loading→error loops.
    if (availabilityStatus !== 'error' || availabilityAutoRetriedRef.current) return;
    availabilityAutoRetriedRef.current = true;
    void refreshAvailability();
  }, [availabilityStatus, refreshAvailability]);

  const handlePullRefresh = useCallback(async () => {
    const tasks: Array<Promise<unknown>> = [loadAccount()];
    if (availabilityStatus === 'error') tasks.push(refreshAvailability());
    await Promise.all(tasks);
  }, [availabilityStatus, loadAccount, refreshAvailability]);

  const displayName = account?.display_name || userInfo?.display_name || userInfo?.username || t('account.user');
  const username = account?.username || userInfo?.username || '--';
  const domain = account?.domain || userInfo?.domain || '--';
  const showUsername = username !== '--' && username !== displayName;
  const showDomain = domain !== '--';

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
        <MobileSafeHeader contentClassName={styles.pageHeader}>
          <h1 className={styles.pageTitle}>{t('navigation.profile')}</h1>
        </MobileSafeHeader>
        <div className={styles.scroll}>
          <MobilePullToRefresh onRefresh={handlePullRefresh}>
            <section className={styles.identity} aria-label={t('account.title')}>
              <div className={styles.avatar} aria-hidden="true">{displayName.charAt(0).toUpperCase() || 'U'}</div>
              <div className={styles.identityCopy}>
                <div className={styles.identityTitleRow}>
                  <h2>{displayName}</h2>
                  {showDomain ? <span className={styles.identityDomain}>{domain}</span> : null}
                </div>
                {showUsername ? <p className={styles.identitySubtitle}>@{username}</p> : null}
                <dl className={styles.identityFacts} aria-label={t('account.accountOverview')}>
                  <div className={styles.identityFactRow}>
                    <dt>{t('account.organization')}</dt>
                    <dd className={styles.identityOrgValue}>
                      <OrganizationSwitcher variant="inline" />
                    </dd>
                  </div>
                </dl>
                {accountStatus === 'error' && (
                  <div className={styles.identityError} role="alert">
                    <span>{t('account.loadFailed')}</span>
                    <button
                      type="button"
                      className={styles.identityRetry}
                      aria-label={t('common.retry')}
                      disabled={accountRetrying}
                      onClick={() => void handleAccountRetry()}
                    >
                      <RedoOutline className={accountRetrying ? styles.identityRetrySpin : undefined} aria-hidden />
                    </button>
                  </div>
                )}
              </div>
            </section>

            <div className={styles.body}>
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
          </MobilePullToRefresh>
        </div>
      </main>
    </MobileTabShell>
  );
}
