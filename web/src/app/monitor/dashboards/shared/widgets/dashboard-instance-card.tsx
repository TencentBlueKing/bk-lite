import React from 'react';
import TimeSelector from '@/components/time-selector';
import { ListItem, TimeSelectorDefaultValue } from '@/types';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '../utils';
import { InstanceSelector } from './instance-selector';

export interface DashboardInstanceCardStyles {
  readonly [key: string]: string | undefined;
}

/** 实例卡内联时间选择器 + 刷新组的配置；传入即在实例选择器右侧渲染，统一头部数据控件布局。 */
export interface DashboardInstanceCardTimeSelectorProps {
  timeDefaultValue: TimeSelectorDefaultValue;
  frequencyList?: ListItem[];
  onTimeChange: (val: number[], originValue: number | null) => void;
  onFrequenceChange: (val: number) => void;
  onRefresh: () => void;
}

export interface DashboardInstanceCardProps {
  instanceName: string;
  metaItems: React.ReactNode[];
  icon: React.ReactNode;
  iconClassName?: string;
  selectorValue?: string;
  selectorLoading?: boolean;
  selectorOptions: readonly { label: string; value: string; searchTokens?: string[] }[];
  onInstanceChange: (value: string) => void;
  selectorPlaceholder?: string;
  selectorTitle?: string;
  clusterOptions?: readonly { label: string; value: string; searchTokens?: string[] }[];
  clusterValue?: string;
  onClusterChange?: (value: string) => void;
  isDashboardMode?: boolean;
  /** 传入时在实例选择器右侧内联渲染时间选择器 + 刷新组（统一布局，单一来源）。 */
  timeSelectorProps?: DashboardInstanceCardTimeSelectorProps;
  styles: DashboardInstanceCardStyles;
}

export function DashboardInstanceCard({
  instanceName,
  metaItems,
  icon,
  iconClassName,
  selectorValue,
  selectorLoading,
  selectorOptions,
  onInstanceChange,
  selectorPlaceholder = '选择实例',
  selectorTitle,
  clusterOptions,
  clusterValue,
  onClusterChange,
  isDashboardMode = true,
  timeSelectorProps,
  styles
}: DashboardInstanceCardProps) {
  const cardClassName = `${styles.instanceCard}${!isDashboardMode && styles.instanceCardFull ? ` ${styles.instanceCardFull}` : ''}`;

  return (
    <div className={cardClassName}>
      <div className={styles.instanceMain}>
        <div className={iconClassName ? `${styles.instanceIcon} ${iconClassName}` : styles.instanceIcon}>
          {icon}
        </div>
        <div className={styles.instanceInfo}>
          <div className={styles.meta}>
            <span className={styles.instanceName}>{instanceName}</span>
            {metaItems.map((item, index) => (
              <React.Fragment key={index}>
                <span className={styles.instanceMetaDivider}>|</span>
                {item}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
      <div className={styles.instanceActions}>
        {clusterOptions && clusterOptions.length > 0 && onClusterChange ? (
          <InstanceSelector
            styles={styles}
            label="集群"
            value={clusterValue}
            options={clusterOptions}
            onChange={onClusterChange}
            placeholder="选择集群"
            title={clusterValue}
            popupWidth={220}
          />
        ) : null}
        <InstanceSelector
          styles={styles}
          value={selectorValue}
          loading={selectorLoading}
          options={selectorOptions}
          onChange={onInstanceChange}
          placeholder={selectorPlaceholder}
          title={selectorTitle}
        />
        {timeSelectorProps ? (
          <div className={styles.toolbarTimeSelector}>
            <TimeSelector
              defaultValue={timeSelectorProps.timeDefaultValue}
              customFrequencyList={timeSelectorProps.frequencyList ?? DEFAULT_REFRESH_FREQUENCY_LIST}
              onChange={timeSelectorProps.onTimeChange}
              onFrequenceChange={timeSelectorProps.onFrequenceChange}
              onRefresh={timeSelectorProps.onRefresh}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
