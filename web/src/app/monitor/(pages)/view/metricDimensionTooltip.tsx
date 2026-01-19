'use client';
import React, { useState, useCallback } from 'react';
import { Tooltip, Spin } from 'antd';
import { UnorderedListOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

interface DimensionDataItem {
  label: string;
  value: number | string;
}

interface MetricDimensionTooltipProps {
  instanceId: string;
  metricName: string;
  monitorObjectId: React.Key;
}

const MetricDimensionTooltip: React.FC<MetricDimensionTooltipProps> = ({
  instanceId,
  metricName,
  monitorObjectId,
}) => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const [loading, setLoading] = useState<boolean>(false);
  const [dimensionData, setDimensionData] = useState<DimensionDataItem[]>([]);
  const [hasLoaded, setHasLoaded] = useState<boolean>(false);

  const fetchDimensionData = useCallback(async () => {
    if (hasLoaded) return;

    setLoading(true);
    try {
      const data = await get(
        `/monitor/api/monitor_instance/${monitorObjectId}/metric_dimensions/`,
        {
          params: {
            instance_id: instanceId,
            metric_name: metricName,
          },
        }
      );
      setDimensionData(data || []);
      setHasLoaded(true);
    } catch (error) {
      console.error('Failed to fetch dimension data:', error);
      setDimensionData([]);
    } finally {
      setLoading(false);
    }
  }, [instanceId, metricName, monitorObjectId, hasLoaded, get]);

  const handleOpenChange = (open: boolean) => {
    if (open && !hasLoaded) {
      fetchDimensionData();
    }
  };

  const tooltipContent = (
    <div className="min-w-[200px] max-w-[400px] max-h-[300px] overflow-y-auto">
      {loading ? (
        <div className="flex justify-center items-center py-[20px]">
          <Spin size="small" />
        </div>
      ) : dimensionData.length > 0 ? (
        <div className="flex flex-col gap-[4px]">
          {dimensionData.map((item, index) => (
            <div key={index} className="whitespace-nowrap">
              {item.label}: {item.value}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center text-[var(--color-text-3)] py-[10px]">
          {t('common.noResult')}
        </div>
      )}
    </div>
  );

  return (
    <Tooltip
      title={tooltipContent}
      placement="left"
      trigger="hover"
      onOpenChange={handleOpenChange}
    >
      <UnorderedListOutlined className="text-[var(--color-text-3)] hover:text-[var(--color-primary)] cursor-pointer ml-[8px]" />
    </Tooltip>
  );
};

export default MetricDimensionTooltip;
