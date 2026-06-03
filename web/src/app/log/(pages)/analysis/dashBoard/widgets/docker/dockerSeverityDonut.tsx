import React, { useMemo } from 'react';
import DockerDonutChart from './dockerDonutChart';
import { DOCKER_LEVEL_ORDER } from './dockerLogLevel';

const toNumber = (value: unknown) => {
  const num = parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const DockerSeverityDonut: React.FC<any> = (props) => {
  const normalizedRawData = useMemo(() => {
    if (!Array.isArray(props.rawData) || props.rawData.length === 0) {
      return props.rawData;
    }

    const summary = props.rawData[0] || {};
    const total = toNumber(summary.total_count);
    const errorCount = toNumber(summary.error_count);
    const warnCount = toNumber(summary.warn_count);
    const infoCount = toNumber(summary.info_count);
    const debugCount = toNumber(summary.debug_count);
    const unknownCount = Math.max(
      total - errorCount - warnCount - infoCount - debugCount,
      0
    );

    const counts = {
      ERROR: errorCount,
      WARN: warnCount,
      INFO: infoCount,
      DEBUG: debugCount,
      UNKNOWN: unknownCount
    };

    return DOCKER_LEVEL_ORDER.filter((level) => counts[level] > 0).map(
      (level) => ({ level, cnt: counts[level] })
    );
  }, [props.rawData]);

  const normalizedConfig = {
    ...props.config,
    displayMaps: {
      key: 'level',
      value: 'cnt'
    }
  };

  return (
    <DockerDonutChart
      {...props}
      rawData={normalizedRawData}
      config={normalizedConfig}
    />
  );
};

export default DockerSeverityDonut;
