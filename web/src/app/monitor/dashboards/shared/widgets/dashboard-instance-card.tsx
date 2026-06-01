import React from 'react';
import { InstanceSelector } from './instance-selector';

export interface DashboardInstanceCardStyles {
  readonly [key: string]: string | undefined;
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
  isDashboardMode?: boolean;
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
  isDashboardMode = true,
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
        <InstanceSelector
          styles={styles}
          value={selectorValue}
          loading={selectorLoading}
          options={selectorOptions}
          onChange={onInstanceChange}
          placeholder={selectorPlaceholder}
          title={selectorTitle}
        />
      </div>
    </div>
  );
}
