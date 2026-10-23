import React from 'react';
import { Breadcrumb, Button, Dropdown, Select } from 'antd';
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
import { dashboardModeOptions } from '../utils/pro-dashboard';

export interface DashboardPageHeaderStyles {
  readonly [key: string]: string | undefined;
}

export interface DashboardModeOption {
  labelKey: string;
  fallback: string;
  value: string;
  /** 无该视图能力时仍展示，置灰且不可点。 */
  disabled?: boolean;
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
  /** 默认标题旁单 pill 下拉。选项很多时用 select。无能力的项仍留在菜单里并置灰。 */
  modeControl?: 'segmented' | 'select' | 'pill';
  modeOptions?: readonly DashboardModeOption[];
  styles: DashboardPageHeaderStyles;
}

/** 菜单固定这三项。调用方没列入、或标了 disabled，就置灰不可点。 */
const MODE_CATALOG = [
  { labelKey: 'dashboardMode', fallback: '传统仪表盘', value: 'dashboard' },
  { labelKey: 'categoryTabMode', fallback: '专业仪表盘', value: 'category' },
  { labelKey: 'metricsMode', fallback: '全量指标', value: 'metrics' }
] as const;

/** 未声明对象能力时按「无专业盘」：专业项置灰。 */
const DISPLAY_MODE_OPTIONS: readonly DashboardModeOption[] = dashboardModeOptions('');

export const resolveDashboardModeMenu = (
  provided: readonly DashboardModeOption[] | undefined,
  labelOf: (labelKey: string, fallback: string) => string
) => {
  const byValue = new Map((provided ?? DISPLAY_MODE_OPTIONS).map((item) => [item.value, item]));
  return MODE_CATALOG.map((item) => {
    const given = byValue.get(item.value);
    return {
      value: item.value,
      label: labelOf(given?.labelKey ?? item.labelKey, given?.fallback ?? item.fallback),
      disabled: given ? Boolean(given.disabled) : true
    };
  });
};

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
  const menuItems = resolveDashboardModeMenu(modeOptions, (labelKey, fallback) => common(labelKey, fallback));
  const currentModeLabel = menuItems.find((item) => item.value === displayMode)?.label ?? '';
  const showModePill = modeControl !== 'select' && menuItems.length >= 2;
  const chooseMode = (key: string) => {
    const item = menuItems.find((entry) => entry.value === key);
    if (!item || item.disabled) return;
    onDisplayModeChange(key as 'dashboard' | 'metrics');
  };
  const modeSwitcher = modeControl === 'select' && menuItems.length >= 2 ? (
    <Select
      size="middle"
      className={[styles.modeSelect, 'min-w-[280px] max-md:w-full max-md:min-w-0'].filter(Boolean).join(' ')}
      value={displayMode}
      options={menuItems}
      aria-label={common('viewSwitcher', '视图')}
      popupMatchSelectWidth
      onChange={(value) => chooseMode(String(value))}
    />
  ) : null;
  const modePill = showModePill ? (
    <Dropdown
      trigger={['click']}
      menu={{
        selectable: true,
        selectedKeys: [displayMode],
        items: menuItems.map((item) => ({
          key: item.value,
          label: item.label,
          disabled: item.disabled
        })),
        onClick: ({ key }) => chooseMode(key)
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
      <div className={[styles.pageTitleRow, showModePill ? styles.pageTitleRowPill : ''].filter(Boolean).join(' ')}>
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
