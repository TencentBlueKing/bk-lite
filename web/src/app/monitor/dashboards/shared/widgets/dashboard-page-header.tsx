import React from 'react';
import { Breadcrumb, Button, Segmented } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import TimeSelector from '@/components/time-selector';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { ListItem, TimeSelectorDefaultValue } from '@/types';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '../utils';
import {
  getDashboardReturnNavigation
} from '../utils/return-navigation';
import { localizeDashboardReturnLabel, tDashboardText, useDashboardText } from '../utils/content-i18n';

export interface DashboardPageHeaderStyles {
  readonly [key: string]: string | undefined;
}

export interface DashboardPageHeaderProps {
  title: string;
  displayMode: 'dashboard' | 'metrics';
  onDisplayModeChange: (mode: 'dashboard' | 'metrics') => void;
  timeDefaultValue: TimeSelectorDefaultValue;
  frequencyList?: ListItem[];
  onTimeChange: (val: number[], originValue: number | null) => void;
  onFrequenceChange: (val: number) => void;
  onRefresh: () => void;
  /** 是否在标题行内渲染时间选择器；置 false 时由调用方自行放置（默认 true，保持原行为）。 */
  showTimeSelector?: boolean;
  /** SNMP / NetFlow / sFlow 跨路由切换（与展示模式 Segmented 并列）。 */
  viewSwitchSlot?: React.ReactNode;
  styles: DashboardPageHeaderStyles;
}

const DISPLAY_MODE_OPTIONS = [
  { labelKey: 'dashboardMode', fallback: '监控仪表盘', value: 'dashboard' },
  { labelKey: 'metricsMode', fallback: '全量指标', value: 'metrics' }
] as const;

export function DashboardPageHeader({
  title,
  displayMode,
  onDisplayModeChange,
  timeDefaultValue,
  frequencyList = DEFAULT_REFRESH_FREQUENCY_LIST,
  onTimeChange,
  onFrequenceChange,
  onRefresh,
  showTimeSelector = true,
  viewSwitchSlot,
  styles
}: DashboardPageHeaderProps) {
  const { t, common } = useDashboardText();
  const localizedTitle = title.endsWith(' 全量指标')
    ? `${title.slice(0, -' 全量指标'.length)} ${common('fullMetrics', '全量指标')}`
    : tDashboardText(t, title);
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnNavigation = getDashboardReturnNavigation(searchParams, localizedTitle);
  const backLabel = localizeDashboardReturnLabel(t, searchParams);
  const breadcrumbItems = returnNavigation.breadcrumbItems.map((item) => ({
    ...item,
    title: typeof item.title === 'string' ? tDashboardText(t, item.title) : item.title
  }));
  const onBack = () => router.push(returnNavigation.href);

  const backButton = (
    <Button
      className={`${styles.toolbarBackBtn ?? ''} inline-flex max-w-[260px] items-center`}
      icon={<ArrowLeftOutlined aria-hidden="true" />}
      onClick={onBack}
      aria-label={backLabel}
    >
      <EllipsisWithTooltip
        className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap"
        text={backLabel}
      />
    </Button>
  );

  return (
    <div className={styles.pageTitleRow}>
      <Breadcrumb className={styles.breadcrumb} items={breadcrumbItems} />
      <div className={styles.titleControlsRow}>
        <h1 className={styles.title}>{localizedTitle}</h1>
        <div className={styles.controlsWrap}>
          {viewSwitchSlot}
          <Segmented
            size="middle"
            className={styles.modeSegmented}
            value={displayMode}
            options={DISPLAY_MODE_OPTIONS.map((item) => ({
              value: item.value,
              label: common(item.labelKey, item.fallback)
            }))}
            onChange={(value) => onDisplayModeChange(value as 'dashboard' | 'metrics')}
          />
          {showTimeSelector ? (
            <div className={styles.toolbarTimeSelector}>
              <TimeSelector
                appearance="toolbar"
                defaultValue={timeDefaultValue}
                customFrequencyList={frequencyList.map((item) => ({
                  ...item,
                  label: tDashboardText(t, String(item.label))
                }))}
                onChange={onTimeChange}
                onFrequenceChange={onFrequenceChange}
                onRefresh={onRefresh}
              />
            </div>
          ) : null}
          {styles.actionButtons ? (
            <div className={styles.actionButtons}>{backButton}</div>
          ) : (
            backButton
          )}
        </div>
      </div>
    </div>
  );
}
