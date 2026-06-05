import React from 'react';
import { Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import TimeSelector from '@/components/time-selector';
import { ListItem, TimeSelectorDefaultValue } from '@/types';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '../utils';

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
  /** 是否在标题行内渲染时间选择器；置 false 时由调用方自行放置（默认 true，保持原行为）。 */
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
  styles
}: DashboardPageHeaderProps) {
  return (
    <div className={styles.pageTitleRow}>
      <div className={styles.titleBlock}>
        <h1 className={styles.title}>{title}</h1>
      </div>
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
            <Button className={styles.toolbarBackBtn} icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
          </div>
        ) : (
          <Button className={styles.toolbarBackBtn} icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
        )}
      </div>
    </div>
  );
}
