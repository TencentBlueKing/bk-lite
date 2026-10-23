'use client';

import { Button, Popconfirm, Spin, Switch } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
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
  onUnbind: () => void;
}

/** Edit mode. Opens the existing resource binding drawer from the node settings panel. */
const stripButtonStyle = {
  boxSizing: 'border-box' as const,
  height: 24,
  paddingInline: 8,
  borderRadius: 6,
  fontSize: 12,
  flexShrink: 0,
};

export const NodeBindingStrip = ({ bound, loading, name, model, dotColor, onOpen, onUnbind }: NodeBindingStripProps) => {
  const { t } = useTranslation();
  const full = [name, model].filter(Boolean).join(' · ');
  const showName = bound && (loading || Boolean(name));

  return (
    <div className="box-border flex w-full min-w-0 max-w-full items-center gap-2">
      {showName ? (
        loading ? (
          <div className="flex min-w-0 flex-1 items-center">
            <Spin size="small" />
          </div>
        ) : (
          <div className="flex min-w-0 flex-1 flex-col gap-0.5" title={full}>
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dotColor }} />
              <span className="min-w-0 truncate text-xs font-medium text-[var(--color-text-1)]">{name}</span>
            </div>
            {model ? (
              <span className="min-w-0 truncate pl-3 text-xs text-[var(--color-text-3)]">{model}</span>
            ) : null}
          </div>
        )
      ) : null}
      {bound ? (
        <>
          <Popconfirm
            title={t('opsAnalysis.architecture.bindingUnbindConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={onUnbind}
          >
            <Button
              size="small"
              danger
              data-testid="architecture-binding-unbind"
              style={stripButtonStyle}
            >
              {t('opsAnalysis.architecture.bindingStripUnbind')}
            </Button>
          </Popconfirm>
          <Button
            size="small"
            onClick={onOpen}
            data-testid="architecture-binding-rebind"
            style={{
              ...stripButtonStyle,
              color: 'var(--color-primary)',
              borderColor: 'var(--color-primary)',
            }}
          >
            {t('opsAnalysis.architecture.bindingStripRebind')}
          </Button>
        </>
      ) : (
        <Button
          size="small"
          block
          icon={<LinkOutlined />}
          onClick={onOpen}
          data-testid="architecture-binding-strip"
          style={{
            ...stripButtonStyle,
            width: '100%',
            color: 'var(--color-primary)',
            borderColor: 'var(--color-primary)',
            background: 'var(--color-bg)',
          }}
        >
          {t('opsAnalysis.architecture.bindingDrawerTitle')}
        </Button>
      )}
    </div>
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
        <Switch
          size="small"
          checked={followAlert}
          onChange={onFollowAlert}
          style={{ width: 44, minWidth: 44 }}
        />
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
