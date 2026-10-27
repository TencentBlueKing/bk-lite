'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppstoreOutlined, ExportOutlined, RightOutlined, SyncOutlined } from '@ant-design/icons';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useHomepageApi } from '@/app/ops-analysis/api/homepage';
import { useHomepagePreference } from '@/app/ops-analysis/context/homepagePreference';
import {
  homepagePreferenceNavigationTarget,
} from '@/app/ops-analysis/utils/homepageLanding';
import { hasAppAccess } from '@/context/appCapabilities/access';
import { useClientData } from '@/context/client';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { message } from 'antd';
import {
  OPS_ANALYSIS_APP,
  OPS_ANALYSIS_VIEW_PATH,
  canShowDashboardSettingsLink,
  followGlobalDescription,
  homepageParentRightLabel,
  homepageRadioChecked,
  menuGrantsOpsAnalysisView,
  personalDashboardCaption,
  type HomepagePersonalMode,
  type MenuPermissionNode,
} from './homepageMenu';

const readDashboardName = async (
  getAccess: (dashboardId: string | number) => Promise<{ status?: string; name?: string }>,
  dashboardId: number,
): Promise<string | null> => {
  try {
    const access = await getAccess(dashboardId);
    const raw = access?.status === 'ok' ? access.name : '';
    return typeof raw === 'string' && raw.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
};

export const useHomepageMenu = (_groupId?: string) => {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { get } = useApiClient();
  const { getAccess } = useHomepageApi();
  const {
    state,
    isLoading: preferenceLoading,
    reload: reloadState,
    applyPersonal,
  } = useHomepagePreference();
  const { clientData, loading: clientLoading } = useClientData();
  const [applying, setApplying] = useState(false);
  const [viewAllowed, setViewAllowed] = useState<boolean | null>(null);
  const [adminName, setAdminName] = useState<string | null>(null);
  const [personalName, setPersonalName] = useState<string | null>(null);
  const [personalNameResolved, setPersonalNameResolved] = useState(false);
  const applyingRef = useRef(false);
  const adminNameIdRef = useRef<number | null>(null);
  const personalNameIdRef = useRef<number | null>(null);

  const hasModule = hasAppAccess(clientData, OPS_ANALYSIS_APP);

  useEffect(() => {
    if (clientLoading) {
      setViewAllowed(null);
      return;
    }
    if (!hasModule) {
      setViewAllowed(false);
      return;
    }
    let cancelled = false;
    setViewAllowed(null);
    get<MenuPermissionNode[]>('/core/api/get_user_menus/', {
      params: { name: OPS_ANALYSIS_APP },
      suppressErrorNotification: true,
    })
      .then((menus) => {
        if (!cancelled) {
          setViewAllowed(menuGrantsOpsAnalysisView(menus));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setViewAllowed(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clientLoading, get, hasModule]);

  useEffect(() => {
    let cancelled = false;
    const personalId = state?.personal_mode === 'dashboard' && state.personal_dashboard_id
      ? state.personal_dashboard_id
      : null;
    const adminId = state?.global_mode === 'dashboard' && state.global_dashboard_id
      ? state.global_dashboard_id
      : null;

    // 同一块盘重新拉取时留着已显示的名称。先清空再填回会让说明折行，浮层高度跟着跳。
    if (personalNameIdRef.current !== personalId) {
      personalNameIdRef.current = personalId;
      setPersonalName(null);
      setPersonalNameResolved(!personalId && state !== null);
    }
    if (adminNameIdRef.current !== adminId) {
      adminNameIdRef.current = adminId;
      setAdminName(null);
    }

    if (personalId) {
      void readDashboardName(getAccess, personalId).then((name) => {
        if (cancelled) {
          return;
        }
        setPersonalName(name);
        setPersonalNameResolved(true);
      });
    }
    if (adminId) {
      void readDashboardName(getAccess, adminId).then((name) => {
        if (cancelled) {
          return;
        }
        setAdminName(name);
      });
    }

    return () => {
      cancelled = true;
    };
  }, [getAccess, state]);

  const commit = useCallback(async (action: 'clear' | 'pin_workbench') => {
    if (applyingRef.current) {
      return false;
    }
    applyingRef.current = true;
    setApplying(true);
    try {
      // 共享状态用接口返回值更新；普通页停留，门户首页上按新偏好落地。
      const next = await applyPersonal({ action });
      message.success(
        action === 'clear'
          ? t('common.homepageFollowGlobalSuccess')
          : t('common.homepagePinWorkbenchSuccess'),
      );
      const search = searchParams?.toString() ? `?${searchParams.toString()}` : '';
      const target = homepagePreferenceNavigationTarget(pathname, search, next);
      if (target) {
        router.replace(target);
      }
      return true;
    } catch {
      return false;
    } finally {
      applyingRef.current = false;
      setApplying(false);
    }
  }, [applyPersonal, pathname, router, searchParams, t]);

  const followGlobal = useCallback(
    () => commit('clear'),
    [commit],
  );

  const pinWorkbench = useCallback(
    () => commit('pin_workbench'),
    [commit],
  );

  const openDashboardSettings = useCallback(() => {
    router.push(OPS_ANALYSIS_VIEW_PATH);
  }, [router]);

  const personalMode = state?.personal_mode ?? null;

  return {
    personalMode,
    preferenceLoading,
    adminDashboardName: adminName?.trim() ? adminName.trim() : null,
    personalDashboardCaption: personalDashboardCaption(
      personalMode,
      personalName,
      personalNameResolved,
      t('common.homepagePersonalDashboardFallback'),
    ),
    showSettingsLink: canShowDashboardSettingsLink({
      clientLoading,
      hasModule,
      viewAllowed,
    }),
    applying: applying || preferenceLoading,
    reloadState,
    followGlobal,
    pinWorkbench,
    openDashboardSettings,
  };
};

interface HomepageSwitcherRowProps {
  mode: HomepagePersonalMode | null;
  /** 个人仪表盘名称；仅 mode=dashboard 时用于右侧展示。 */
  dashboardName?: string | null;
  onToggle?: () => void;
}

export const HomepageSwitcherRow = ({ mode, dashboardName, onToggle }: HomepageSwitcherRowProps) => {
  const { t } = useTranslation();
  const right = homepageParentRightLabel(mode, dashboardName);
  const rightText = right
    ? (right.kind === 'text' ? right.value : t(right.key))
    : '';

  return (
    <div
      data-testid="homepage-switcher-row"
      className="flex w-full min-w-0 cursor-pointer items-center gap-3"
      onClick={(event) => {
        event.stopPropagation();
        onToggle?.();
      }}
    >
      <span className="shrink-0">{t('common.homepage')}</span>
      <span className="flex min-w-0 flex-1 items-center justify-end gap-1 text-xs text-[var(--color-text-4)]">
        <span className="truncate">{rightText}</span>
        <RightOutlined className="shrink-0 text-[10px]" />
      </span>
    </div>
  );
};

const OptionGlyph = ({ variant }: { variant: 'follow' | 'workbench' }) => (
  <span
    data-testid={variant === 'follow' ? 'homepage-option-icon-follow' : 'homepage-option-icon-workbench'}
    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-bg)] text-[13px] text-[var(--color-primary)]"
    aria-hidden
  >
    {variant === 'follow' ? <SyncOutlined /> : <AppstoreOutlined />}
  </span>
);

export interface HomepageSwitcherPanelProps {
  personalMode: HomepagePersonalMode | null;
  adminDashboardName: string | null;
  personalDashboardCaption: string | null;
  showSettingsLink: boolean;
  applying: boolean;
  onFollow: () => void;
  onPinWorkbench: () => void;
  onOpenSettings: () => void;
}

export const HomepageSwitcherPanel = ({
  personalMode,
  adminDashboardName,
  personalDashboardCaption: dashboardCaption,
  showSettingsLink,
  applying,
  onFollow,
  onPinWorkbench,
  onOpenSettings,
}: HomepageSwitcherPanelProps) => {
  const { t } = useTranslation();
  const followHint = followGlobalDescription(
    t('common.homepageFollowGlobalHint'),
    (name) => t('common.homepageFollowGlobalCurrent', '（当前：{name}）', { name }),
    adminDashboardName,
  );
  const options = [
    {
      key: 'follow' as const,
      title: t('common.homepageFollowGlobal'),
      hint: followHint,
      onSelect: onFollow,
    },
    {
      key: 'workbench' as const,
      title: t('common.homepagePinWorkbench'),
      hint: t('common.homepagePinWorkbenchHint'),
      onSelect: onPinWorkbench,
    },
  ];

  const settingsSelected = personalMode === 'dashboard';
  const settingsHint = settingsSelected
    ? (dashboardCaption
      ? t('common.homepageCurrentHomepage', '当前首页：{name}', { name: dashboardCaption })
      : null)
    : t('common.homepageDashboardSettingsHint');

  return (
    <div
      data-testid="homepage-switcher-panel"
      className="w-[300px]"
      onClick={(event) => event.stopPropagation()}
    >
      <div
        data-testid="homepage-panel-title"
        className="border-b border-[var(--color-border-2)] px-3 py-1.5 text-sm font-medium text-[var(--color-text-1)]"
      >
        {t('common.homepagePanelTitle')}
      </div>
      <div role="radiogroup" aria-label={t('common.homepagePanelTitle')} className="flex flex-col gap-0.5 px-2 py-1">
        {options.map((option) => {
          const checked = homepageRadioChecked(personalMode, option.key);
          return (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-label={option.title}
              data-selected={checked ? 'true' : 'false'}
              disabled={applying}
              className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--color-primary)] disabled:cursor-wait ${
                checked
                  ? 'bg-[var(--color-primary-bg-active)]'
                  : 'hover:bg-[var(--color-fill-1)]'
              }`}
              onClick={option.onSelect}
            >
              <OptionGlyph variant={option.key} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-[var(--color-text-1)]">
                  {option.title}
                </span>
                <span className="mt-0.5 block text-[11px] leading-4 text-[var(--color-text-3)]">
                  {option.hint}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {showSettingsLink ? (
        <button
          type="button"
          data-testid="homepage-dashboard-settings"
          data-selected={settingsSelected ? 'true' : 'false'}
          disabled={applying}
          className="flex w-full cursor-pointer flex-col gap-0.5 border-t border-[var(--color-border-2)] px-3 py-2 text-left hover:bg-[var(--color-fill-1)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--color-primary)] disabled:cursor-wait"
          onClick={onOpenSettings}
        >
          <span className="flex items-center gap-1.5">
            <span
              className={`min-w-0 truncate text-sm ${
                settingsSelected
                  ? 'text-[var(--color-primary)]'
                  : 'text-[var(--color-text-1)]'
              }`}
            >
              {t('common.homepageDashboardSettings')}
            </span>
            <ExportOutlined
              className={`shrink-0 text-xs ${
                settingsSelected
                  ? 'text-[var(--color-primary)]'
                  : 'text-[var(--color-text-3)]'
              }`}
            />
          </span>
          {settingsHint ? (
            <span
              data-testid="homepage-personal-dashboard-caption"
              className="block truncate text-[11px] leading-4 text-[var(--color-text-3)]"
            >
              {settingsHint}
            </span>
          ) : null}
        </button>
      ) : null}
    </div>
  );
};
