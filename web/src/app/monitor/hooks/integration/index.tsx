import { useCallback, useEffect, useState } from 'react';
import {
  getCachedObjectConfig,
  loadObjectConfig
} from './configLoaders';
import {
  PluginConfigRequest,
  resolvePluginConfig
} from './configContracts';

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
    (data: PluginConfigRequest) => {
      const objectConfig = resolveConfig(data.objectName);
      const pluginCfg =
        objectConfig?.plugins?.[data.pluginName]?.getPluginCfg(data);
      return resolvePluginConfig(pluginCfg);
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
