import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getCachedObjectConfig,
  loadObjectConfig
} from './configLoaders';
import {
  PluginConfigRequest,
  resolvePluginConfig
} from './configContracts';
import {
  applyObjectConfigLoadReject,
  applyObjectConfigLoadSuccess,
  createObjectConfigLoadState,
  retryObjectConfigLoad,
  switchObjectConfigLoad
} from './objectConfigLoad';

/**
 * 按当前对象按需加载配置，避免一次挂载全部对象 hook/模块。
 */
export const useMonitorConfig = (objectName?: string | null) => {
  const [configVersion, setConfigVersion] = useState(0);
  const [loadState, setLoadState] = useState(() =>
    createObjectConfigLoadState({
      objectName,
      cached: !objectName || !!getCachedObjectConfig(objectName)
    })
  );
  const trackedObjectRef = useRef(objectName);

  useEffect(() => {
    if (trackedObjectRef.current === objectName) {
      return;
    }
    trackedObjectRef.current = objectName;
    const cached = !objectName || !!getCachedObjectConfig(objectName);
    setLoadState((prev) => switchObjectConfigLoad(prev, { objectName, cached }));
  }, [objectName]);

  const retry = useCallback(() => {
    setLoadState((prev) => retryObjectConfigLoad(prev));
  }, []);

  useEffect(() => {
    if (!objectName || loadState.status !== 'waiting') {
      return;
    }
    const generation = loadState.generation;
    let active = true;
    loadObjectConfig(objectName).then(
      () => {
        if (!active) return;
        setLoadState((prev) => applyObjectConfigLoadSuccess(prev, generation));
        setConfigVersion((v) => v + 1);
      },
      () => {
        if (!active) return;
        setLoadState((prev) => applyObjectConfigLoadReject(prev, generation));
      }
    );
    return () => {
      active = false;
    };
  }, [objectName, loadState.status, loadState.generation]);

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
    ready: loadState.status === 'ready',
    error: loadState.status === 'error',
    retry,
    resolveConfig
  };
};
