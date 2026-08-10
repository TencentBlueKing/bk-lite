import React from 'react';
import { Button, Segmented } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import DashboardWorkspaceHeader from '@/components/dashboard-workspace-header';
import TimeSelector from '@/components/time-selector';
import type { ListItem, TimeSelectorDefaultValue } from '@/types';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '@/app/monitor/components/monitor-dashboard-widgets/runtime';

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
  onBack: () => void;
  showTimeSelector?: boolean;
  styles: DashboardPageHeaderStyles;
}

const DISPLAY_MODE_OPTIONS = [
  { label: '监控仪表盘', value: 'dashboard' },
  { label: '全量指标', value: 'metrics' },
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
  onBack,
  showTimeSelector = true,
  styles,
}: DashboardPageHeaderProps) {
  const backButton = (
    <Button
      className={styles.toolbarBackBtn}
      icon={<ArrowLeftOutlined aria-hidden="true" />}
      onClick={onBack}
      aria-label="返回"
    >
      返回
    </Button>
  );

  return (
    <DashboardWorkspaceHeader
      as="h1"
      title={title}
      headerRowClassName={styles.pageTitleRow}
      contentClassName={styles.titleBlock}
      titleClassName={styles.title}
      controls={
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
      }
    />
  );
}
