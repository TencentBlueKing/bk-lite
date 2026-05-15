import React, { useMemo } from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

// Query 返回 4 个直接互斥区间字段：cnt_lt01 / cnt_01_1 / cnt_1_10 / cnt_gt10
// displayMaps.key = 'bucket', displayMaps.value = 'cnt'
const BUCKETS = [
  { field: 'cnt_lt01', label: '快速 <0.1s' },
  { field: 'cnt_01_1', label: '普通 0.1–1s' },
  { field: 'cnt_1_10', label: '慢 1–10s' },
  { field: 'cnt_gt10', label: '严重 >10s' }
];

const toNumber = (value: unknown) => {
  const num = parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const MysqlDonut: React.FC<any> = (props) => {
  const normalizedRawData = useMemo(() => {
    if (!Array.isArray(props.rawData) || props.rawData.length === 0) {
      return props.rawData;
    }

    const summary = props.rawData[0] || {};
    const buckets = BUCKETS.map(({ field, label }) => ({
      bucket: label,
      cnt: Math.max(toNumber(summary[field]), 0)
    }));

    return buckets.filter((item) => item.cnt > 0);
  }, [props.rawData]);

  return <DockerDonutChart {...props} rawData={normalizedRawData} />;
};

export default MysqlDonut;
