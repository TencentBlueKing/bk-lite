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
  styles: DashboardPageHeaderStyles;
}

const DISPLAY_MODE_OPTIONS = [
  { label: '监控仪表盘', value: 'dashboard' },
  { label: '全量指标', value: 'metrics' }
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
  styles
}: DashboardPageHeaderProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnNavigation = getDashboardReturnNavigation(searchParams, title);
  const onBack = () => router.push(returnNavigation.href);

  const backButton = (
    <Button
      className={`${styles.toolbarBackBtn ?? ''} inline-flex max-w-[260px] items-center`}
      icon={<ArrowLeftOutlined aria-hidden="true" />}
      onClick={onBack}
      aria-label={returnNavigation.label}
    >
      <EllipsisWithTooltip
        className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap"
        text={returnNavigation.label}
      />
    </Button>
  );

  return (
    <div className={styles.pageTitleRow}>
      <div className={styles.titleBlock}>
        <Breadcrumb className={styles.breadcrumb} items={returnNavigation.breadcrumbItems} />
        <h1 className={styles.title}>{title}</h1>
      </div>
      <div className={styles.controlsWrap}>
        <Segmented
          size="middle"
          className={styles.modeSegmented}
          value={displayMode}
          options={[...DISPLAY_MODE_OPTIONS]}
          onChange={(value) => onDisplayModeChange(value as 'dashboard' | 'metrics')}
        />
        {showTimeSelector ? (
            <div className={styles.toolbarTimeSelector}>
            <TimeSelector
              appearance="toolbar"
              defaultValue={timeDefaultValue}
              customFrequencyList={frequencyList}
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
  );
}
