'use client';

import React, { useMemo } from 'react';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import { resolveAppDescription, resolveAppDisplayName, resolveAppTag } from '@/utils/appDisplayName';
import { useClientData } from '@/context/client';
import { useThemeMode } from '@/theme';
import { useUserInfoContext } from '@/context/userInfo';

interface PortalConsolePreviewProps {
  portalName: string;
  portalLogoUrl: string;
  portalFaviconUrl: string;
  watermarkEnabled: boolean;
  watermarkText: string;
}

const TAG_STYLES = [
  { backgroundColor: 'var(--color-primary-bg-active)', color: 'var(--color-primary)' },
  { backgroundColor: 'var(--color-fill-1)', color: 'var(--color-text-2)' },
  { backgroundColor: 'var(--color-fill-2)', color: 'var(--color-text-1)' },
  { backgroundColor: 'var(--color-bg-2)', color: 'var(--color-text-1)' },
];

const getInitials = (value: string) => {
  const normalized = value.trim();
  if (!normalized) {
    return 'BL';
  }

  const asciiParts = normalized.match(/[A-Za-z0-9]+/g);
  if (asciiParts && asciiParts.length >= 2) {
    return `${asciiParts[0][0]}${asciiParts[1][0]}`.slice(0, 2).toUpperCase();
  }
  if (asciiParts && asciiParts.length === 1) {
    return asciiParts[0].slice(0, 2).toUpperCase();
  }

  return normalized.slice(0, 2).toUpperCase();
};

const applyTemplate = (template: string, portalName: string, variables: Record<string, string>) => {
  const safeTemplate = template || `${portalName} · ${variables.username} · ${variables.date}`;
  return safeTemplate.replace(/\$\{([a-zA-Z0-9_]+)\}/g, (match, key) => {
    if (key === 'portalName') {
      return portalName;
    }

    return variables[key] ?? match;
  });
};

const PortalConsolePreview: React.FC<PortalConsolePreviewProps> = ({
  portalName,
  portalLogoUrl,
  portalFaviconUrl,
  watermarkEnabled,
  watermarkText,
}) => {
  const { t } = useTranslation();
  const { clientData, appConfigList, loading, appConfigLoading } = useClientData();
  const { mode } = useThemeMode();
  const { username, displayName } = useUserInfoContext();

  const displayApps = useMemo(() => {
    const sourceApps = (appConfigList.length > 0 ? appConfigList : clientData).filter((item) => item.name !== 'ops-console');
    return sourceApps.slice(0, 4);
  }, [appConfigList, clientData]);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const watermarkPreviewText = useMemo(() => applyTemplate(watermarkText, portalName, {
    username: username || 'admin',
    chname: displayName || (t('system.settings.portal.variableChineseNameFallback') as string),
    email: 'admin@bklite.local',
    phone: '13800138000',
    date: today,
  }), [watermarkText, portalName, username, displayName, today, t]);
  const previewTitleTemplate = t('system.settings.portal.previewTitle') as string;
  const previewDescriptionTemplate = t('system.settings.portal.previewDescription') as string;
  const previewTitle = (previewTitleTemplate || '欢迎使用{portalName}控制台').replace('{portalName}', portalName);
  const previewDescription = (previewDescriptionTemplate || '').replace('{portalName}', portalName);
  const previewApps = displayApps.slice(0, 6);
  const portalInitials = useMemo(() => getInitials(portalName), [portalName]);
  const hasFavicon = Boolean(portalFaviconUrl?.trim());
  const hasLogo = Boolean(portalLogoUrl?.trim());

  const PreviewBrowserIdentity = ({ size, textSize }: { size: string; textSize: string }) => {
    if (hasFavicon) {
      return <img src={portalFaviconUrl} alt={portalName} className={`${size} shrink-0 rounded-md object-contain`} />;
    }

    return (
      <span className={`inline-flex ${size} shrink-0 items-center justify-center rounded-md bg-[linear-gradient(135deg,#4a8dff_0%,#2f6fed_100%)] ${textSize} font-bold text-white`}>
        {portalInitials}
      </span>
    );
  };

  const PreviewConsoleIdentity = ({ className }: { className: string }) => {
    if (hasLogo) {
      return <img src={portalLogoUrl} alt={portalName} className={className} />;
    }

    if (hasFavicon) {
      return <img src={portalFaviconUrl} alt={portalName} className={className} />;
    }

    return (
      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[linear-gradient(135deg,#4a8dff_0%,#2f6fed_100%)] text-[11px] font-bold text-white">
        {portalInitials}
      </span>
    );
  };

  return (
    <div className="overflow-hidden rounded-[14px] border border-(--color-border-1) bg-(--color-bg) shadow-[0_10px_28px_var(--color-portal-card-shadow)]">
      <div className="px-4 pt-4 text-base font-semibold text-(--color-text-1)">
        {t('system.settings.portal.preview')}
      </div>
      <div className="p-4">
        <div className="overflow-hidden rounded-2xl border border-(--color-portal-preview-border) bg-(--color-bg-1)">
          <div className="border-b border-(--color-portal-preview-divider) bg-(--color-portal-surface-soft)">
            <div className="rounded-t-[20px] bg-(--color-portal-surface-soft) px-4 pt-3">
              <div className="flex h-11 w-full items-center gap-2.5 rounded-t-2xl border border-(--color-portal-preview-border-strong) bg-(--color-bg-1) px-4 shadow-[inset_0_1px_0_var(--color-portal-surface-overlay)]">
                <PreviewBrowserIdentity size="h-5 w-5" textSize="text-[11px]" />
                <span className="truncate text-[10px] font-semibold text-(--color-text-2)">{portalName}</span>
              </div>
            </div>
          </div>

          <div
            className={`relative min-h-140 overflow-hidden bg-cover bg-top px-6 pb-6 pt-7 ${mode === 'dark' ? 'bg-[url(/app/console_bg_dark.jpg)]' : 'bg-[url(/app/console_bg.jpg)]'}`}
          >
            <div className="relative z-2 -mx-6 -mt-7 mb-7 border-b border-(--color-portal-preview-divider) bg-(--color-portal-preview-shell) px-5 py-3 shadow-[0_6px_18px_var(--color-portal-card-shadow)] backdrop-blur-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-center gap-2.5">
                  <PreviewConsoleIdentity className="block h-8 w-auto max-w-36 shrink-0 object-contain" />
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="max-w-36 truncate text-[10px] font-bold text-(--color-text-1)">{portalName}</span>
                    <span className="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-lg border border-(--color-portal-preview-border-strong) bg-(--color-bg-1) px-2.5 text-[9px] font-semibold leading-none text-(--color-text-2) shadow-[0_3px_8px_var(--color-portal-card-shadow)]">
                      控制台
                      <span className="ml-1 text-[8px]">▼</span>
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <span key={index} className="h-6.5 w-6.5 rounded-lg border border-(--color-portal-preview-border) bg-(--color-portal-preview-icon-bg) shadow-[inset_0_1px_0_var(--color-portal-surface-overlay)]" />
                  ))}
                </div>
              </div>
            </div>

            <div className="relative z-2 mb-8">
              <h1 className="mb-3 text-[24px] font-bold leading-tight text-(--color-text-1)">{previewTitle}</h1>
              <p className="max-w-[72%] text-[12px] leading-6 text-(--color-text-2)">{previewDescription}</p>

              <div className="mt-5 flex items-center gap-3">
                <div className="flex items-center rounded-full border border-(--color-border-1) bg-(--color-portal-surface-overlay) text-[11px] shadow-sm">
                  <span className="rounded-full bg-(--color-primary) px-3 py-1 text-white">{t('system.settings.portal.previewDate')}</span>
                  <span className="px-3 text-(--color-text-2)">{today.replace(/-/g, '/')}</span>
                </div>
                <span className="rounded-full bg-(--color-primary) px-4 py-1 text-[11px] font-semibold text-white shadow-sm">
                  {t('system.settings.portal.previewCustomSettings')}
                </span>
              </div>
            </div>

            <div className="relative z-2 grid grid-cols-2 gap-4">
              {(loading || appConfigLoading ? Array.from({ length: 6 }).map((_, index) => ({ id: `skeleton-${index}` })) : previewApps).map((app) => {
                if ('id' in app && typeof app.id === 'string' && app.id.startsWith('skeleton-')) {
                  return <div key={app.id} className="h-36 rounded-xl bg-(--color-portal-preview-shell) p-4 shadow-md" />;
                }

                const realApp = app as (typeof displayApps)[number];

                return (
                  <div
                    key={realApp.id}
                    className="relative flex h-36 flex-col justify-between rounded-xl bg-(--color-bg-1) p-4 shadow-md"
                  >
                    <div className="absolute right-4 top-4">
                      <span className="inline-flex items-center rounded-md bg-(--color-primary) px-2 py-1 text-[10px] font-semibold text-white">
                        {t('system.settings.portal.previewEnter')}
                      </span>
                    </div>

                    <div>
                      <div className="mb-2 flex items-center gap-2">
                        <Icon type={realApp.icon || realApp.name} className="text-[38px] text-(--color-primary)" />
                        <div className="truncate text-[13px] font-bold text-(--color-text-1)">{resolveAppDisplayName(realApp, t)}</div>
                      </div>

                      <div className="mb-3 flex flex-wrap gap-1.5">
                        {(realApp.tags || []).slice(0, 3).map((tag, tagIndex) => (
                          <span
                            key={`${realApp.id}-${tag}`}
                            className="rounded-md px-1.5 py-0.5 text-[9px] font-medium"
                            style={TAG_STYLES[tagIndex % TAG_STYLES.length]}
                          >
                            {resolveAppTag(tag, t)}
                          </span>
                        ))}
                      </div>
                    </div>

                    <p className="line-clamp-2 text-[10px] leading-4 text-(--color-text-2)">{resolveAppDescription(realApp, t)}</p>
                  </div>
                );
              })}
            </div>

            {watermarkEnabled && (
              <div className="pointer-events-none absolute inset-0 z-1 grid grid-cols-2 content-center justify-items-center gap-x-16 gap-y-20 px-8 py-8">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="select-none whitespace-nowrap text-[13px] tracking-[0.08em] text-(--color-text-4) transform-[rotate(-24deg)]">
                    {watermarkPreviewText}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortalConsolePreview;
