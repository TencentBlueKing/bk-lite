import React, { useState, useEffect, useCallback } from 'react';
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
import ComTable from '../widgets/comTable';

const componentMap: Record<string, React.ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
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
  const [tableLoading, setTableLoading] = useState(false);
  const [tableQueryReady, setTableQueryReady] = useState(false);
  const [dataValidation, setDataValidation] = useState<{
    isValid: boolean;
    message?: string;
  } | null>(null);
  const [tableQueryParams, setTableQueryParams] = useState<Record<string, any>>(
    {},
  );
  const { getSourceDataByApiId } = useDataSourceApi();

  const handleTableQueryChange = useCallback((params: Record<string, any>) => {
    setTableQueryReady(true);
    setTableQueryParams((prev) => {
      if (JSON.stringify(prev) === JSON.stringify(params || {})) {
        return prev;
      }
      return params || {};
    });
  }, []);

  const fetchData = async () => {
    if (!config?.dataSource) {
      setLoading(false);
      setTableLoading(false);
      setDataValidation(null);
      return;
    }

    const isTableChart = chartType === 'table';

    // 检查权限
    if (dataSource?.hasAuth === false) {
      setLoading(false);
      setTableLoading(false);
      setRawData(null);
      setDataValidation({
        isValid: false,
        message: t('common.noAuth'),
      });
      return;
    }

    try {
      if (isTableChart) {
        setTableLoading(true);
      } else {
        setLoading(true);
      }
      setDataValidation(null);

      const data = await fetchWidgetData({
        config,
        dataSource,
        globalTimeRange,
        extraParams: chartType === 'table' ? tableQueryParams : undefined,
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
      if (isTableChart) {
        setTableLoading(false);
      } else {
        setLoading(false);
      }
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
            item.data.length > 0,
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
      case 'table':
        // Table handles its own data format, skip chart validation
        return { isValid: true };
      default:
        return { isValid: true };
    }
  };

  useEffect(() => {
    if (!config?.dataSource) {
      return;
    }

    if (chartType === 'table' && !tableQueryReady) {
      return;
    }

    fetchData();
  }, [
    config,
    globalTimeRange,
    refreshKey,
    dataSource?.hasAuth,
    tableQueryParams,
    chartType,
    tableQueryReady,
  ]);

  useEffect(() => {
    if (chartType !== 'table') {
      return;
    }
    setTableQueryReady(false);
    setTableQueryParams({});
    setTableLoading(false);
    setLoading(false);
  }, [chartType, config?.dataSource]);

  const renderError = (message: string) => (
    <div className="h-full flex flex-col items-center justify-center">
      <ExclamationCircleOutlined
        style={{ color: '#faad14', fontSize: '24px', marginBottom: '12px' }}
      />
      <span style={{ fontSize: '14px', color: '#666' }}>{message}</span>
    </div>
  );

  if (loading && chartType !== 'table') {
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
      dataValidation.message || t('dashboard.dataCannotRenderAsChart'),
    );
  }

  return (
    <Component
      rawData={rawData}
      loading={chartType === 'table' ? tableLoading : loading}
      config={config}
      dataSource={dataSource}
      globalTimeRange={globalTimeRange}
      refreshKey={refreshKey}
      onReady={onReady}
      onQueryChange={chartType === 'table' ? handleTableQueryChange : undefined}
      {...otherProps}
    />
  );
};

export default WidgetWrapper;
