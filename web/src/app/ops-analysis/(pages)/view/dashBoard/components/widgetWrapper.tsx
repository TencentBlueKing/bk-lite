import React, { useState, useEffect } from 'react';
import { Spin } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { BaseWidgetProps } from '@/app/ops-analysis/types/dashBoard';
import { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { fetchWidgetData } from '../../../../utils/widgetDataTransform';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import ComPie from '../widgets/comPie';
import ComLine from '../widgets/comLine';
import ComBar from '../widgets/comBar';

const componentMap: Record<string, React.ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
};

interface WidgetWrapperProps extends BaseWidgetProps {
  chartType?: string;
  dataSource?: DatasourceItem;
}

const WidgetWrapper: React.FC<WidgetWrapperProps> = ({
  chartType,
  config,
  globalTimeRange,
  refreshKey,
  onReady,
  dataSource,
  ...otherProps
}) => {
  const { t } = useTranslation();
  const [rawData, setRawData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [dataValidation, setDataValidation] = useState<{
    isValid: boolean;
    message?: string;
  } | null>(null);
  const { getSourceDataByApiId } = useDataSourceApi();

  const fetchData = async () => {
    if (!config?.dataSource) {
      setLoading(false);
      setDataValidation(null);
      return;
    }

    // 检查权限
    if (dataSource?.hasAuth === false) {
      setLoading(false);
      setRawData(null);
      setDataValidation({
        isValid: false,
        message: t('common.noAuth'),
      });
      return;
    }

    try {
      setLoading(true);
      setDataValidation(null);

      const data = await fetchWidgetData({
        config,
        globalTimeRange,
        getSourceDataByApiId,
      });

      setRawData(data);

      const validation = validateChartData(data, chartType);
      setDataValidation(validation);
    } catch (err) {
      console.error('获取数据失败:', err);
      setRawData(null);
      setDataValidation({
        isValid: false,
        message: t('dashboard.dataFetchFailed'),
      });
    } finally {
      setLoading(false);
    }
  };

  // 提取数据校验逻辑
  const validateChartData = (data: unknown, type?: string) => {
    const isDataEmpty = () => {
      if (!data) return true;
      if (Array.isArray(data) && data.length === 0) return true;

      if (Array.isArray(data) && data.length > 0) {
        const hasValidData = data.some(
          (item) =>
            item &&
            item.data &&
            Array.isArray(item.data) &&
            item.data.length > 0
        );
        if (!hasValidData) return true;
      }

      return false;
    };

    if (isDataEmpty()) {
      return { isValid: true };
    }

    const errorMessage = t('dashboard.dataFormatMismatch');
    switch (type) {
      case 'pie':
        return ChartDataTransformer.validatePieData(data, errorMessage);
      case 'line':
      case 'bar':
        return ChartDataTransformer.validateLineBarData(data, errorMessage);
      default:
        return { isValid: true };
    }
  };

  useEffect(() => {
    if (config?.dataSource) {
      fetchData();
    }
  }, [config, globalTimeRange, refreshKey, dataSource?.hasAuth]);

  const renderError = (message: string) => (
    <div className="h-full flex flex-col items-center justify-center">
      <ExclamationCircleOutlined
        style={{ color: '#faad14', fontSize: '24px', marginBottom: '12px' }}
      />
      <span style={{ fontSize: '14px', color: '#666' }}>{message}</span>
    </div>
  );

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin spinning={loading} />
      </div>
    );
  }

  const Component = chartType ? componentMap[chartType] : null;
  if (!Component) {
    return renderError(`${t('dashboard.unknownComponentType')}: ${chartType}`);
  }

  // 如果数据校验失败，显示错误提示
  if (dataValidation && !dataValidation.isValid) {
    return renderError(
      dataValidation.message || t('dashboard.dataCannotRenderAsChart')
    );
  }

  return (
    <Component
      rawData={rawData}
      loading={loading}
      config={config}
      globalTimeRange={globalTimeRange}
      refreshKey={refreshKey}
      onReady={onReady}
      {...otherProps}
    />
  );
};

export default WidgetWrapper;
