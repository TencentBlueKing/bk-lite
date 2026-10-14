'use client';

import React from 'react';
import { Button, Select } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useRouter, useSearchParams } from 'next/navigation';
import TimeSelector from '@/components/time-selector';
import { HOST_DETAIL_LAYOUT_OPTIONS, type HostDetailLayout } from '../detail-layout';
import { localizeDashboardReturnLabel, useDashboardText } from '../../../shared/utils/content-i18n';
import { getDashboardReturnNavigation } from '../../../shared/utils/return-navigation';
import { DEFAULT_REFRESH_FREQUENCY_LIST } from '../../../shared/utils';
import type { useSimpleDashboardData } from '../../common/simple-dashboard-core';
import styles from './layered.module.scss';

export default function LayeredToolbar({
  dashboard,
  layout,
  onLayoutChange
}: {
  dashboard: ReturnType<typeof useSimpleDashboardData>;
  layout: HostDetailLayout;
  onLayoutChange: (mode: string) => void;
}) {
  const { common, dt, t } = useDashboardText();
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnNavigation = getDashboardReturnNavigation(searchParams, dashboard.pageTitle);
  const backLabel = localizeDashboardReturnLabel(t, searchParams);
  const meta = dashboard.objectMetaItems
    .map((item) => (typeof item === 'string' ? dt(item) : ''))
    .filter(Boolean)
    .join(' · ');

  return (
    <header className={styles.toolbar}>
      <div className={styles.toolbarMeta}>
        <div className={styles.toolbarLead}>
          <Button
            type="text"
            size="small"
            className={styles.backBtn}
            icon={<ArrowLeftOutlined aria-hidden="true" />}
            aria-label={backLabel}
            onClick={() => router.push(returnNavigation.href)}
          />
          <div>
            <div className={styles.toolbarName}>{dashboard.resolvedInstanceName}</div>
            {meta ? <div className={styles.toolbarSub}>{meta}</div> : null}
          </div>
        </div>
      </div>
      <div className={styles.toolbarControls}>
        <TimeSelector
          appearance="toolbar"
          defaultValue={dashboard.timeDefaultValue}
          customFrequencyList={DEFAULT_REFRESH_FREQUENCY_LIST}
          onChange={dashboard.onTimeChange}
          onFrequenceChange={dashboard.setFrequence}
          onRefresh={dashboard.onRefresh}
        />
        <Select
          size="middle"
          className={styles.viewSelect}
          classNames={{ popup: { root: styles.dropdown } }}
          value={layout}
          aria-label={common('viewSwitcher', '视图')}
          options={HOST_DETAIL_LAYOUT_OPTIONS.map((item) => ({
            value: item.value,
            label: common(item.labelKey, item.fallback)
          }))}
          onChange={onLayoutChange}
        />
      </div>
    </header>
  );
}
