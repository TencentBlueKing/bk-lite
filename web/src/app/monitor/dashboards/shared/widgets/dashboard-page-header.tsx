import React from 'react';
import { Breadcrumb, Button, Dropdown, Segmented, Select } from 'antd';
import { ArrowLeftOutlined, DownOutlined } from '@ant-design/icons';
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

export interface DashboardModeOption {
  labelKey: string;
  fallback: string;
  value: string;
}

export interface DashboardPageHeaderProps {
  title: string;
  /** 主机详情会多一个分类页签值，其它对象仍是 dashboard / metrics。 */
  displayMode: string;
  onDisplayModeChange: (mode: 'dashboard' | 'metrics') => void;
  timeDefaultValue: TimeSelectorDefaultValue;
  frequencyList?: ListItem[];
  onTimeChange: (val: number[], originValue: number | null) => void;
  onFrequenceChange: (val: number) => void;
  onRefresh: () => void;
  /** 是否在标题行内渲染时间选择器；置 false 时由调用方自行放置（默认 true，保持原行为）。 */
  showTimeSelector?: boolean;
  /** SNMP / NetFlow / sFlow 跨路由切换（与展示模式控件并列）。 */
  viewSwitchSlot?: React.ReactNode;
  /** 默认两档分段按钮。选项变多时改用下拉；主机详情用标题旁 pill。 */
  modeControl?: 'segmented' | 'select' | 'pill';
  modeOptions?: readonly DashboardModeOption[];
  styles: DashboardPageHeaderStyles;
}

const DISPLAY_MODE_OPTIONS = [
  { labelKey: 'dashboardMode', fallback: '经典布局', value: 'dashboard' },
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
  modeControl = 'segmented',
  modeOptions,
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
  const resolvedModeOptions = modeOptions ?? DISPLAY_MODE_OPTIONS;
  const hasProfessionalMode = resolvedModeOptions.some((item) => item.value === 'category');
  const usePill = modeControl === 'pill' && hasProfessionalMode;
  const modeItems = resolvedModeOptions.map((item) => ({
    value: item.value,
    label: common(item.labelKey, item.fallback)
  }));
  const currentModeLabel = modeItems.find((item) => item.value === displayMode)?.label ?? '';
  const modeSwitcher = usePill || modeControl === 'pill' ? null : modeControl === 'select' ? (
    <Select
      size="middle"
      className={[styles.modeSelect, 'min-w-[280px] max-md:w-full max-md:min-w-0'].filter(Boolean).join(' ')}
      value={displayMode}
      options={modeItems}
      aria-label={common('viewSwitcher', '视图')}
      popupMatchSelectWidth
      onChange={(value) => onDisplayModeChange(value as 'dashboard' | 'metrics')}
    />
  ) : (
    <Segmented
      size="middle"
      className={styles.modeSegmented}
      value={displayMode}
      options={modeItems}
      onChange={(value) => onDisplayModeChange(value as 'dashboard' | 'metrics')}
    />
  );
  const modePill = usePill ? (
    <Dropdown
      trigger={['click']}
      menu={{
        selectable: true,
        selectedKeys: [displayMode],
        items: modeItems.map((item) => ({
          key: item.value,
          label: item.label
        })),
        onClick: ({ key }) => onDisplayModeChange(key as 'dashboard' | 'metrics')
      }}
    >
      <button
        type="button"
        className={styles.viewModePill}
        data-view-mode-pill=""
        aria-haspopup="menu"
        aria-label={common('viewSwitcher', '视图')}
      >
        <span>{currentModeLabel}</span>
        <DownOutlined className={styles.viewModeCaret} aria-hidden="true" />
      </button>
    </Dropdown>
  ) : null;

  const backButton = (
    <Button
      type="link"
      className={[styles.backLink, 'inline-flex max-w-[260px] items-center'].filter(Boolean).join(' ')}
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
    <>
      <div className={styles.headerCrumb}>
        <Breadcrumb className={styles.breadcrumb} items={breadcrumbItems} />
      </div>
      <div className={[styles.pageTitleRow, usePill ? styles.pageTitleRowPill : ''].filter(Boolean).join(' ')}>
        <div className={styles.titleControlsRow}>
          <div className={styles.titleLead}>
            <h1 className={styles.title}>{localizedTitle}</h1>
            {modePill}
            {viewSwitchSlot}
            {modeSwitcher}
          </div>
          <div className={styles.controlsWrap}>
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
    </>
  );
}
