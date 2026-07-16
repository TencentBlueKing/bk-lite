import React from 'react';
import { Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import DashboardWorkspaceHeader from '@/components/dashboard-workspace-header';
import TimeSelector from '@/components/time-selector';
import type { ListItem, TimeSelectorDefaultValue } from '@/types';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '@/components/monitor-dashboard-widgets/runtime';

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
  return (
    <DashboardWorkspaceHeader
      as="h1"
      title={title}
      headerRowClassName={styles.pageTitleRow}
      contentClassName={styles.titleBlock}
      titleClassName={styles.title}
      controls={
        <div className={styles.controlsWrap}>
          <div className={styles.modeTabs}>
            <button
              type="button"
              className={`${styles.modeTab} ${displayMode === 'dashboard' ? styles.modeTabActive : ''}`}
              onClick={() => onDisplayModeChange('dashboard')}
            >
              监控仪表盘
            </button>
            <button
              type="button"
              className={`${styles.modeTab} ${displayMode === 'metrics' ? styles.modeTabActive : ''}`}
              onClick={() => onDisplayModeChange('metrics')}
            >
              全量指标
            </button>
          </div>
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
            <div className={styles.actionButtons}>
              <Button
                className={styles.toolbarBackBtn}
                icon={<ArrowLeftOutlined />}
                onClick={onBack}
              >
                返回
              </Button>
            </div>
          ) : (
            <Button
              className={styles.toolbarBackBtn}
              icon={<ArrowLeftOutlined />}
              onClick={onBack}
            >
              返回
            </Button>
          )}
        </div>
      }
    />
  );
}
