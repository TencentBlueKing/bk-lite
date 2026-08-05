import { useCallback, useEffect, useState } from 'react';
import { TableDataItem } from '@/app/monitor/types';
import {
  getCachedObjectConfig,
  loadObjectConfig
} from './configLoaders';

const buildDefaultPluginCfg = (mode: 'manual' | 'auto' | 'edit') => {
  const commonConfig = {
    collect_type: '',
    config_type: [],
    collector: '',
    instance_type: '',
    object_name: ''
  };
  if (mode === 'auto') {
    return {
      ...commonConfig,
      formItems: null,
      initTableItems: {},
      defaultForm: {},
      columns: [],
      getParams: () => ({})
    };
  }
  return {
    ...commonConfig,
    getParams: () => ({
      instance_id: '',
      instance_name: ''
    }),
    getFormItems: () => null,
    configText: ''
  };
};

/**
 * 按当前对象按需加载配置，避免一次挂载全部对象 hook/模块。
 */
export const useMonitorConfig = (objectName?: string | null) => {
  const [configVersion, setConfigVersion] = useState(0);
  const [ready, setReady] = useState(() => !objectName || !!getCachedObjectConfig(objectName));

  useEffect(() => {
    if (!objectName) {
      setReady(true);
      return;
    }
    let active = true;
    const cached = getCachedObjectConfig(objectName);
    setReady(!!cached);
    loadObjectConfig(objectName).then(() => {
      if (!active) return;
      setConfigVersion((v) => v + 1);
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, [objectName]);

  const resolveConfig = useCallback(
    (name?: string | null) => {
      // configVersion 仅用于在加载完成后触发重新 resolve。
      void configVersion;
      return getCachedObjectConfig(name);
    },
    [configVersion]
  );

  const getPlugin = useCallback(
    (data: {
      objectName: string;
      mode: 'manual' | 'auto' | 'edit';
      pluginName: string;
      dataSource?: TableDataItem[];
      onTableDataChange?: (data: TableDataItem[]) => void;
    }) => {
      const objectConfig = resolveConfig(data.objectName);
      const pluginCfg =
        objectConfig?.plugins?.[data.pluginName]?.getPluginCfg(data);
      return pluginCfg || buildDefaultPluginCfg(data.mode);
    },
    [resolveConfig]
  );

  const config = objectName
    ? { [objectName]: resolveConfig(objectName) }
    : {};

  return {
    config,
    getPlugin,
    ready,
    resolveConfig
  };
};
