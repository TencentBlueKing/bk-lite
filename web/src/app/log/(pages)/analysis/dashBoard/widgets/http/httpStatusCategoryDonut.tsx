import React, { useMemo } from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';
import {
  getHttpStatusCategory,
  HTTP_STATUS_CATEGORY_KEYS
} from './statusCodeCategory';

const toNumber = (value: unknown) => {
  const num = parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const HttpStatusCategoryDonut: React.FC<any> = (props) => {
  const normalizedRawData = useMemo(() => {
    if (!Array.isArray(props.rawData) || props.rawData.length === 0) {
      return props.rawData;
    }

    const labels = props.config?.displayMaps?.labels || {};
    const summary = props.rawData.reduce(
      (acc: Record<string, number>, item: Record<string, unknown>) => {
        const category = getHttpStatusCategory(
          item['http.response.status_code']
        );
        acc[category] =
          (acc[category] || 0) + Math.max(toNumber(item.reqcount), 0);
        return acc;
      },
      {}
    );

    return HTTP_STATUS_CATEGORY_KEYS.map((category) => ({
      bucket: labels[category] || category,
      count: summary[category] || 0
    })).filter((item: { count: number }) => item.count > 0);
  }, [props.config?.displayMaps?.labels, props.rawData]);

  return (
    <DockerDonutChart
      {...props}
      rawData={normalizedRawData}
      config={{
        ...props.config,
        displayMaps: {
          ...props.config?.displayMaps,
          key: 'bucket',
          value: 'count'
        }
      }}
    />
  );
};

export default HttpStatusCategoryDonut;
