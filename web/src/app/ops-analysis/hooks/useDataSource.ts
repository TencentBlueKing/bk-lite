import { useState } from 'react';
import dayjs from 'dayjs';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  type DataSourceFormParams as FormParams,
  processDataSourceFormParamsForSubmit,
} from '@/app/ops-analysis/utils/dataSourceFormParams';


export const useDataSourceManager = () => {
  const [selectedDataSource, setSelectedDataSource] = useState<DatasourceItem | undefined>();
  const {
    dataSources,
    dataSourcesLoading,
    fetchDataSources,
    loadCanvasDataSources,
  } = useOpsAnalysis();
  const { getDataSourceDetail } = useDataSourceApi();

  const findDataSource = (
    dataSourceId?: string | number
  ): DatasourceItem | undefined => {
    if (dataSourceId) {
      const id = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
      return dataSources.find((ds) => ds.id === id);
    }
    return undefined;
  };

  const ensureDataSource = async (
    dataSourceId?: string | number
  ): Promise<DatasourceItem | undefined> => {
    if (!dataSourceId) {
      return undefined;
    }

    const existing = findDataSource(dataSourceId);
    if (existing) {
      return existing;
    }

    const id = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
    try {
      return await getDataSourceDetail(id);
    } catch {
      return undefined;
    }
  };

  const setDefaultParamValues = (params: ParamItem[], formParams: FormParams): void => {
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
          if (param.value && (typeof param.value === 'string' || typeof param.value === 'number')) {
            formParams[param.name] = dayjs(param.value);
          } else {
            formParams[param.name] = null;
          }
          break;
        default:
          formParams[param.name] = param.value ?? '';
      }
    });
  };

  const restoreUserParamValues = (dataSourceParams: ParamItem[], formParams: FormParams): void => {
    dataSourceParams.forEach((param) => {
      if (param.value !== undefined) {
        if (param.type === 'date' && param.value) {
          if (typeof param.value === 'string' || typeof param.value === 'number') {
            formParams[param.name] = dayjs(param.value);
          }
        } else {
          formParams[param.name] = param.value;
        }
      }
    });
  };

  const processFormParamsForSubmit = (
    formParams: FormParams,
    sourceParams: ParamItem[]
  ): ParamItem[] => processDataSourceFormParamsForSubmit(formParams, sourceParams);
  return {
    dataSources,
    dataSourcesLoading,
    selectedDataSource,
    setSelectedDataSource,
    fetchDataSources,
    loadCanvasDataSources,
    findDataSource,
    ensureDataSource,
    setDefaultParamValues,
    restoreUserParamValues,
    processFormParamsForSubmit,
  };
};
