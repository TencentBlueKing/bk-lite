'use client';

import { Spin, Switch } from 'antd';
import { LinkOutlined, RightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface NodeBindingStripProps {
  bound: boolean;
  loading: boolean;
  /** Resource name, or the localized reason the resource cannot be shown. */
  name: string;
  /** Model display name; empty when the resource cannot be shown. */
  model: string;
  dotColor: string;
  onOpen: () => void;
}

/**
 * Edit mode. One line at the bottom of the icon settings header (Isoflow fixes
 * its height): long text is cut with an ellipsis and never wraps.
 */
export const NodeBindingStrip = ({ bound, loading, name, model, dotColor, onOpen }: NodeBindingStripProps) => {
  const { t } = useTranslation();
  const full = [name, model].filter(Boolean).join(' · ');

  return (
    <button
      type="button"
      className="flex h-full w-full min-w-0 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-left text-xs [font-family:inherit]"
      onClick={onOpen}
      data-testid="architecture-binding-strip"
    >
      <span className="shrink-0 text-[var(--color-text-3)]">
        {t('opsAnalysis.architecture.bindingStripLabel')}
      </span>
      <span className="flex min-w-0 flex-1 items-center" title={bound && !loading ? full : undefined}>
        {!bound ? (
          <span className="text-[var(--color-text-4)]">{t('opsAnalysis.architecture.bindingStripUnbound')}</span>
        ) : loading ? (
          <Spin size="small" />
        ) : (
          <>
            <span className="mr-1.5 inline-block h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: dotColor }} />
            <span className="min-w-0 truncate">
              <span className="font-medium text-[var(--color-text-1)]">{name}</span>
              {model ? <span className="text-[var(--color-text-3)]">{` · ${model}`}</span> : null}
            </span>
          </>
        )}
      </span>
      <span className="flex shrink-0 items-center gap-1 font-medium text-[var(--color-primary)]">
        {bound ? (
          <>
            {t('opsAnalysis.architecture.bindingStripEdit')}
            <RightOutlined className="text-[10px]" />
          </>
        ) : (
          <>
            <LinkOutlined />
            {t('opsAnalysis.architecture.bindingStripBind')}
          </>
        )}
      </span>
    </button>
  );
};

interface RegionAlertSettingsProps {
  followAlert: boolean;
  iconTotal: number;
  iconBound: number;
  onFollowAlert: (enabled: boolean) => void;
}

/** Edit mode. Shown at the top of the area settings panel. */
export const RegionAlertSettings = ({
  followAlert,
  iconTotal,
  iconBound,
  onFollowAlert,
}: RegionAlertSettingsProps) => {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-2" data-testid="architecture-region-settings">
      <label className="flex items-center justify-between gap-3 text-sm text-[var(--color-text-1)]">
        <span>{t('opsAnalysis.architecture.followAlertSwitch')}</span>
        <Switch size="small" checked={followAlert} onChange={onFollowAlert} />
      </label>
      <p className="m-0 text-xs text-[var(--color-text-3)]">
        {t('opsAnalysis.architecture.followAlertHint')}
      </p>
      <p className="m-0 text-xs text-[var(--color-text-2)]">
        {t('opsAnalysis.architecture.regionIconCount', undefined, {
          total: iconTotal,
          bound: iconBound,
        })}
      </p>
    </section>
  );
};
