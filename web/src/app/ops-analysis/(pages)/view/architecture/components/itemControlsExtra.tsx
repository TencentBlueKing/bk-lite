'use client';

import { useMemo } from 'react';
import { ConfigProvider, Select, Spin, Switch } from 'antd';
import {
  columnOptionValue,
  visibleColumns,
  type MetricChoice,
  type MetricColumn,
} from '../binding/displayMetrics';
import { LinkOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import MoreActionsDropdown, { type MoreActionsDropdownItem } from '@/components/more-actions-dropdown';

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
export const NodeBindingStrip = ({ bound, loading, name, model, dotColor, onOpen, onUnbind }: NodeBindingStripProps) => {
  const { t } = useTranslation();
  const full = [name, model].filter(Boolean).join(' · ');
  const showName = bound && (loading || Boolean(name));
  const actions = useMemo<MoreActionsDropdownItem[]>(() => [
    {
      key: 'rebind',
      label: t('opsAnalysis.architecture.bindingStripRebind'),
      onClick: onOpen,
    },
    {
      key: 'unbind',
      label: t('opsAnalysis.architecture.bindingStripUnbind'),
      danger: true,
      confirm: { title: t('opsAnalysis.architecture.bindingUnbindConfirm') },
      onClick: onUnbind,
    },
  ], [onOpen, onUnbind, t]);

  return (
    <div className="flex w-full min-w-0 flex-col gap-1.5">
      <div className="text-xs font-medium leading-[1.4] text-[var(--color-text-3)]">
        {t('opsAnalysis.architecture.bindingStripLabel')}
      </div>
      {bound ? (
        <div className="flex w-full min-w-0 items-start gap-1 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] py-1.5 pl-2.5 pr-1">
          {showName ? (
            loading ? (
              <div className="flex min-h-6 min-w-0 flex-1 items-center">
                <Spin size="small" />
              </div>
            ) : (
              <div className="flex min-w-0 flex-1 flex-col gap-0.5 py-0.5" title={full}>
                <div className="flex min-w-0 items-center gap-1.5">
                  <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: dotColor }} />
                  <span className="min-w-0 truncate text-xs font-medium text-[var(--color-text-1)]">{name}</span>
                </div>
                {model ? (
                  <span className="min-w-0 truncate pl-3 text-xs text-[var(--color-text-3)]">{model}</span>
                ) : null}
              </div>
            )
          ) : (
            <div className="min-w-0 flex-1" />
          )}
          <MoreActionsDropdown
            items={actions}
            placement="bottomRight"
            labelAlign="start"
            stopPropagation
            buttonClassName="!h-6 !w-6 !min-w-6 !p-0 text-[var(--color-text-3)]"
            iconStyle={{ fontSize: 14 }}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={onOpen}
          data-testid="architecture-binding-strip"
          className="flex w-full cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-[var(--color-border-1)] bg-transparent px-2.5 py-2 text-left text-xs text-[var(--color-primary)]"
        >
          <LinkOutlined />
          {t('opsAnalysis.architecture.bindingStripBind')}
        </button>
      )}
    </div>
  );
};

interface DisplayMetricsFieldProps {
  columns: MetricColumn[];
  choice: MetricChoice | undefined;
  loading: boolean;
  failed: boolean;
  onChange: (choice: MetricChoice | undefined) => void;
  onRetry?: () => void;
}

const DISPLAY_METRIC_CONTROL_HEIGHT = 28;

/** Edit mode. Sits under the CMDB binding strip. Nothing is shown until the user picks columns. */
export const DisplayMetricsField = ({
  columns,
  choice,
  loading,
  failed,
  onChange,
  onRetry,
}: DisplayMetricsFieldProps) => {
  const { t } = useTranslation();
  const options = columns
    .filter((column) => column.keys.some((key) => !key.startsWith('field::')))
    .map((column) => ({
      label: column.name || column.keys[0],
      value: columnOptionValue(column),
    }));
  const selected = visibleColumns(columns, choice).map(columnOptionValue);

  return (
    <div className="flex w-full min-w-0 flex-col gap-1.5" data-testid="architecture-display-metrics">
      <span className="text-xs font-medium leading-[1.4] text-[var(--color-text-3)]">
        {t('opsAnalysis.architecture.displayMetrics')}
      </span>
      {loading ? (
        <div className="flex min-h-6 items-center">
          <Spin size="small" />
        </div>
      ) : options.length === 0 ? (
        failed ? (
          <div
            role="alert"
            className="flex items-center justify-between gap-2 rounded-md bg-[color-mix(in_srgb,var(--color-fail)_10%,var(--color-bg))] px-2 py-1"
          >
            <span className="min-w-0 text-xs leading-[18px] text-[var(--color-fail)]">
              {t('opsAnalysis.architecture.displayMetricsFailed')}
            </span>
            {onRetry ? (
              <button
                type="button"
                className="shrink-0 cursor-pointer border-0 bg-transparent p-0 text-xs text-[var(--color-primary)]"
                onClick={onRetry}
              >
                {t('common.retry')}
              </button>
            ) : null}
          </div>
        ) : (
          <span className="text-xs text-[var(--color-text-3)]">
            {t('opsAnalysis.architecture.displayMetricsEmpty')}
          </span>
        )
      ) : (
        <ConfigProvider theme={{ token: { controlHeight: DISPLAY_METRIC_CONTROL_HEIGHT } }}>
          <Select
            mode="multiple"
            className="w-full"
            allowClear
            maxTagCount="responsive"
            value={selected}
            options={options}
            placeholder={t('opsAnalysis.architecture.displayMetricsPlaceholder')}
            onChange={(next: string[]) => {
              if (!next.length) {
                onChange(undefined);
                return;
              }
              onChange({
                mode: 'custom',
                keys: next.flatMap((value) => value.split('\n')).filter(Boolean),
              });
            }}
          />
        </ConfigProvider>
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
