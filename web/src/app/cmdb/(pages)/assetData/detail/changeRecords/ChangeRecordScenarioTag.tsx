'use client';

import React from 'react';
import styles from './index.module.scss';
import { SCENARIO_COLORS } from './changeRecordView';

export function ChangeRecordScenarioTag({
  scenario,
  label,
}: {
  scenario: string;
  label: string;
}) {
  const colors =
    SCENARIO_COLORS[scenario] || SCENARIO_COLORS.ordinary_attribute_change;
  return (
    <span
      className={styles.scenarioTag}
      style={{ background: colors.bg, color: colors.text }}
    >
      {label}
    </span>
  );
}
