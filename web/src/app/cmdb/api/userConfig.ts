import { useCallback } from 'react';
import useApiClient from '@/utils/request';

interface ConfigRecord<T = unknown> {
  id: number;
  config_key: string;
  config_value: T;
}

interface UserConfigsMap {
  [key: string]: unknown;
}

export const useUserConfigApi = () => {
  const { get, post, del } = useApiClient();

  const getAllConfigs = useCallback(async (): Promise<UserConfigsMap> => {
    try {
      const response = await get('/cmdb/api/user_configs/');
      const records: ConfigRecord<unknown>[] = response?.data || response || [];
      const configsMap: UserConfigsMap = {};
      records.forEach((record) => {
        configsMap[record.config_key] = record.config_value;
      });
      return configsMap;
    } catch {
      return {};
    }
  }, [get]);

  const createConfig = useCallback(async <T>(configKey: string, value: T): Promise<void> => {
    await post('/cmdb/api/user_configs/', {
      config_key: configKey,
      config_value: value,
    });
  }, [post]);

  const updateConfig = useCallback(async <T>(configKey: string, value: T): Promise<void> => {
    await post('/cmdb/api/user_configs/update_key/', {
      config_key: configKey,
      config_value: value,
    });
  }, [post]);

  const deleteConfig = useCallback(async (configKey: string): Promise<void> => {
    await del(`/cmdb/api/user_configs/by_key/${configKey}/`);
  }, [del]);

  return { getAllConfigs, createConfig, updateConfig, deleteConfig };
};

export interface SavedFilterCondition {
  field: string;
  type: string;
  value?: string | number | boolean | (string | number)[];
  start?: string;
  end?: string;
}

export interface SavedFilterItem {
  id: string;
  name: string;
  filters: SavedFilterCondition[];
}

export interface SavedFiltersConfigValue {
  [modelId: string]: SavedFilterItem[];
}

export const useSavedFiltersApi = () => {
  const { createConfig, updateConfig } = useUserConfigApi();

  const saveFilters = useCallback(async (
    configKey: string,
    allFilters: SavedFiltersConfigValue,
    isNew: boolean
  ): Promise<void> => {
    if (isNew) {
      await createConfig(configKey, allFilters);
    } else {
      await updateConfig(configKey, allFilters);
    }
  }, [createConfig, updateConfig]);

  return { saveFilters };
};
