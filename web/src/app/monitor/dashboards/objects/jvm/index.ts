import React from 'react';
import { ObjectDashboardPage } from '../common/object-dashboard-page';
import { JVM_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';

const JVM_TREND_SECTIONS = [
  { title: '运行趋势', chartTitles: ['堆容量趋势', '线程趋势'] },
  { title: 'GC 专项', chartTitles: ['GC 开销趋势', 'GC 频率趋势'] }
];

export default function JvmDashboard() {
  return React.createElement(ObjectDashboardPage, {
    config: JVM_DASHBOARD_CONFIG,
    styles,
    trendSections: JVM_TREND_SECTIONS
  });
}
