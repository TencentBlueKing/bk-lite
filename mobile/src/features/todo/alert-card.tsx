'use client';

import type { AlertLevel, TodoAlert } from './model';
import { AlertLevelIcon } from './alert-level-icon';
import styles from './todo.module.css';

interface AlertCardProps {
  alert: TodoAlert;
  level?: AlertLevel;
  statusLabel: string;
  operatorLabel: string;
  onOpen: () => void;
}

export function AlertCard({
  alert,
  level,
  statusLabel,
  operatorLabel,
  onOpen,
}: AlertCardProps) {
  const resource = alert.resourceName || alert.sourceName || alert.resourceId || '--';
  const operator = alert.operatorDisplay.trim();
  const levelName = level?.displayName || `L${alert.levelId || '-'}`;
  const title = alert.title || alert.alertId;
  const operatorText = operator ? `${operatorLabel} ${operator}` : '';
  const ariaParts = [levelName, statusLabel, title, resource];
  if (operatorText) ariaParts.push(operatorText);

  return (
    <button
      type="button"
      className={styles.alertCard}
      data-status={alert.status}
      aria-label={ariaParts.join('，')}
      onClick={onOpen}
    >
      <span
        className={styles.severityMark}
        style={level?.color ? { backgroundColor: level.color } : undefined}
        aria-hidden="true"
      />
      <span className={styles.cardBody}>
        <span className={styles.cardTopline}>
          <span className={styles.cardState}>
            <span
              className={styles.levelIdentity}
              style={level?.color ? { color: level.color } : undefined}
            >
              <AlertLevelIcon
                icon={level?.icon}
                className={styles.levelIcon}
              />
              <span className={styles.levelName}>{levelName}</span>
            </span>
            <span className={styles.cardDuration}>{alert.duration || '--'}</span>
          </span>
          <span className={styles.statusPill}>{statusLabel}</span>
        </span>
        <strong className={styles.alertTitle}>{title}</strong>
        <span className={styles.cardResource}>
          <span className={styles.resourceName}>{resource}</span>
          {operatorText ? <span className={styles.operatorName}>{operatorText}</span> : null}
        </span>
      </span>
    </button>
  );
}
