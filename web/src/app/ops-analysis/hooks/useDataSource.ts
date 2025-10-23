import { useState, useEffect } from 'react';
import dayjs from 'dayjs';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';

export const useDataSourceManager = () => {
  const [dataSources, setDataSources] = useState<DatasourceItem[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);
  const [selectedDataSource, setSelectedDataSource] = useState<DatasourceItem | undefined>();
  const { getDataSourceList } = useDataSourceApi();

  const fetchDataSources = async () => {
    try {
      setDataSourcesLoading(true);
      const data: DatasourceItem[] = await getDataSourceList();
      setDataSources(data || []);
      return data || [];
    } catch {
      setDataSources([]);
      return [];
    } finally {
      setDataSourcesLoading(false);
    }
  };

  const findDataSource = (
    dataSourceId?: string | number
  ): DatasourceItem | undefined => {
    if (dataSourceId) {
      const id = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
      return dataSources.find((ds) => ds.id === id);
    }
    return undefined;
  };

  const setDefaultParamValues = (params: ParamItem[], formParams: any): void => {
    params.forEach((param) => {
      switch (param.type) {
        case 'timeRange':
          formParams[param.name] = param.value ?? 10080;
          break;
        case 'boolean':
          formParams[param.name] = param.value ?? false;
          break;
        case 'number':
          formParams[param.name] = param.value ?? 0;
          break;
        case 'date':
          formParams[param.name] = param.value ? dayjs(param.value) : null;
          break;
        default:
          formParams[param.name] = param.value ?? '';
      }
    });
  };

  const restoreUserParamValues = (dataSourceParams: any[], formParams: any): void => {
    dataSourceParams.forEach((param) => {
      if (param.value !== undefined) {
        if (param.type === 'date' && param.value) {
          formParams[param.name] = dayjs(param.value);
        } else {
          formParams[param.name] = param.value;
        }
      }
    });
  };

  const processFormParamsForSubmit = (
    formParams: any,
    sourceParams: ParamItem[]
  ): any[] => {
    const processedParams = { ...formParams };

    sourceParams.forEach((param) => {
      if (param.type === 'date' && processedParams[param.name]) {
        const dateValue = processedParams[param.name];
        if (dateValue && typeof dateValue.format === 'function') {
          processedParams[param.name] = dateValue.format('YYYY-MM-DD HH:mm:ss');
        }
      }
    });

    return sourceParams.map((param) => ({
      ...param,
      value: processedParams[param.name] !== undefined
        ? processedParams[param.name]
        : param.value,
    }));
  };

  useEffect(() => {
    fetchDataSources();
  }, []);

  return {
    dataSources,
    dataSourcesLoading,
    selectedDataSource,
    setSelectedDataSource,
    fetchDataSources,
    findDataSource,
    setDefaultParamValues,
    restoreUserParamValues,
    processFormParamsForSubmit,
  };
};
