'use client';

import type { ComponentProps } from 'react';
import LineChart from '@/components/monitor-line-chart';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';

type MonitorLineChartRuntimeProps = ComponentProps<typeof LineChart>;

const MonitorLineChartRuntime = (props: MonitorLineChartRuntimeProps) => {
  const { findUnitNameById } = useUnitTransform();

  return <LineChart {...props} resolveUnitLabel={findUnitNameById} />;
};

export default MonitorLineChartRuntime;
