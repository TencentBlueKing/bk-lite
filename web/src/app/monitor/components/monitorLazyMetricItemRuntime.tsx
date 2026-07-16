'use client';

import type { ComponentProps } from 'react';
import MonitorLazyMetricItem from '@/components/monitor-lazy-metric-item';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';

type MonitorLazyMetricItemRuntimeProps = ComponentProps<
  typeof MonitorLazyMetricItem
>;

const MonitorLazyMetricItemRuntime = (
  props: MonitorLazyMetricItemRuntimeProps,
) => {
  const { findUnitNameById } = useUnitTransform();

  return (
    <MonitorLazyMetricItem
      {...props}
      resolveUnitLabel={findUnitNameById}
    />
  );
};

export default MonitorLazyMetricItemRuntime;
