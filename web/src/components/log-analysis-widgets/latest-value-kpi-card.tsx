import React from 'react';
import LogKpiCard from '@/components/log-kpi-card';

export interface LogAnalysisLatestValueKpiCardProps {
  rawData: any;
  prevData?: any;
  config?: any;
  [key: string]: any;
}

const calculateLatestMetric = (rawData: any, prevData: any, config: any) => {
  const field = config?.displayMaps?.value;
  if (!field || !Array.isArray(rawData) || rawData.length === 0) {
    return { currentValue: undefined, changePercent: null, trendData: [] };
  }

  const trendData = rawData.map((item: any) => Number(item[field] || 0));
  const currentValue = trendData[trendData.length - 1];
  let changePercent: number | null = null;

  if (Array.isArray(prevData) && prevData.length > 0) {
    const prevValue = Number(prevData[prevData.length - 1]?.[field] || 0);
    if (prevValue !== 0) {
      changePercent = ((currentValue - prevValue) / prevValue) * 100;
    } else if (currentValue > 0) {
      changePercent = 100;
    }
  } else if (trendData.length > 1) {
    const baseValue = trendData[trendData.length - 2];
    if (baseValue !== 0) {
      changePercent = ((currentValue - baseValue) / baseValue) * 100;
    }
  }

  return { currentValue, changePercent, trendData };
};

const LogAnalysisLatestValueKpiCard: React.FC<LogAnalysisLatestValueKpiCardProps> = (
  props
) => {
  return (
    <LogKpiCard
      {...props}
      calculateMetric={
        props?.config?.metricMode === 'latest' ? calculateLatestMetric : undefined
      }
    />
  );
};

export default LogAnalysisLatestValueKpiCard;
