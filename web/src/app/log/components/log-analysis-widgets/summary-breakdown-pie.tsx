import React, { useMemo } from 'react';
import LogAnalysisPie from '@/app/log/components/log-analysis-widgets/pie';

interface SummaryBreakdownBucket {
  field: string;
  label: string;
}

interface LogAnalysisSummaryBreakdownPieProps {
  rawData: any;
  loading?: boolean;
  buckets: SummaryBreakdownBucket[];
  totalField?: string;
  remainderLabel?: string;
  nameField?: string;
  valueField?: string;
}

const toNumber = (value: unknown) => {
  const num = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const LogAnalysisSummaryBreakdownPie: React.FC<LogAnalysisSummaryBreakdownPieProps> = ({
  rawData,
  loading = false,
  buckets,
  totalField,
  remainderLabel,
  nameField = 'name',
  valueField = 'count',
}) => {
  const normalizedRawData = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return rawData;
    }

    const summary = rawData[0] || {};
    const normalizedBuckets = buckets
      .map(({ field, label }) => ({
        [nameField]: label,
        [valueField]: Math.max(toNumber(summary[field]), 0),
      }))
      .filter((item) => toNumber(item[valueField]) > 0);

    if (!remainderLabel || !totalField) {
      return normalizedBuckets;
    }

    const total = toNumber(summary[totalField]);
    const used = normalizedBuckets.reduce(
      (sum, item) => sum + toNumber(item[valueField]),
      0
    );
    const remainder = Math.max(total - used, 0);

    return remainder > 0
      ? [
        ...normalizedBuckets,
        {
          [nameField]: remainderLabel,
          [valueField]: remainder,
        },
      ]
      : normalizedBuckets;
  }, [buckets, nameField, rawData, remainderLabel, totalField, valueField]);

  return (
    <LogAnalysisPie
      rawData={normalizedRawData}
      loading={loading}
      config={{
        displayMaps: {
          key: nameField,
          value: valueField,
        },
      }}
    />
  );
};

export default LogAnalysisSummaryBreakdownPie;
