import { useState, useEffect } from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useUserInfoContext } from '@/context/userInfo';
import { addAuthToDataSources } from '@/app/ops-analysis/utils/permissionChecker';
import { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';

type FormParamValue = string | number | boolean | Dayjs | [number, number] | null;
type FormParams = Record<string, FormParamValue>;

export const useDataSourceManager = () => {
  const [dataSources, setDataSources] = useState<DatasourceItem[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);
  const [selectedDataSource, setSelectedDataSource] = useState<DatasourceItem | undefined>();
  const { getDataSourceList } = useDataSourceApi();
  const { selectedGroup } = useUserInfoContext();

  const fetchDataSources = async () => {
    try {
      setDataSourcesLoading(true);
      const data: DatasourceItem[] = await getDataSourceList({
        all_groups: true,
      });
      // 添加权限检查
      const dataWithAuth = addAuthToDataSources(data || [], selectedGroup?.id);
      setDataSources(dataWithAuth);
      return dataWithAuth;
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
          processedParams[param.name] = value.format('YYYY-MM-DD HH:mm:ss');
        } else if (typeof value === 'string' || typeof value === 'number') {
          processedParams[param.name] = value;
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
