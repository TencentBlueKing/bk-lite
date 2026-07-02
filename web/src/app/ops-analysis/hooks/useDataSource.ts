import { useState } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';

type FormParamValue = string | number | boolean | Dayjs | [number, number] | null;
type FormParams = Record<string, FormParamValue>;

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
  ): ParamItem[] => {
    const processedParams: Record<string, string | number | boolean | [number, number] | null> = {};

    sourceParams.forEach((param) => {
      const value = formParams[param.name];

      if (param.type === 'date' && value) {
        // 转换 Dayjs 为字符串
        if (dayjs.isDayjs(value)) {
          processedParams[param.name] = formatOpsRequestTime(value);
        } else if (typeof value === 'string' || typeof value === 'number') {
          processedParams[param.name] = formatOpsRequestTime(value);
        }
      } else if (value !== undefined && value !== null) {
        // 其他类型直接使用（已经是正确的类型）
        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || Array.isArray(value)) {
          processedParams[param.name] = value as string | number | boolean | [number, number];
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
