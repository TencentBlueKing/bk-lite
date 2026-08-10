import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import {
  extractDataSourceItems,
  mapDynamicItems,
  resolveDynamicSourceId,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';

export type ParamInputOptionsState =
  | { status: 'idle'; options: [] }
  | { status: 'loading'; options: [] }
  | { status: 'success'; options: InputOption[] }
  | { status: 'error'; options: [] };

export interface ParamInputOptionsLoad {
  sync: boolean;
  initial: ParamInputOptionsState;
  promise: Promise<ParamInputOptionsState | null>;
}

interface OptionsApi {
  getDataSourceList: (params?: unknown) => Promise<unknown>;
  getSourceDataByApiId: (id: number, params?: unknown) => Promise<unknown>;
}

const typedOption = (option: InputOption) => [option.label, typeof option.value, option.value];

export const buildParamInputOptionsResultKey = (
  configKey: string,
  options: InputOption[],
): string => JSON.stringify([configKey, options.map(typedOption)]);

export interface ParamInputOptionsNotifier {
  notify: (
    resultKey: string,
    options: InputOption[],
    callback?: (options: InputOption[]) => void,
  ) => boolean;
}

export const createParamInputOptionsNotifier = (): ParamInputOptionsNotifier => {
  let lastNotifiedResultKey: string | undefined;
  return {
    notify: (resultKey, options, callback) => {
      if (!callback || resultKey === lastNotifiedResultKey) return false;
      lastNotifiedResultKey = resultKey;
      callback(options);
      return true;
    },
  };
};

export const getParamInputConfigKey = (config?: InputControlConfig): string => {
  if (!config) return 'none';
  if (config.control === 'input') return 'input';
  const source = config.optionsSource;
  if (source.type === 'static') {
    return JSON.stringify(['static', config.control, source.staticItems.map(typedOption)]);
  }
  return JSON.stringify([
    'dynamic', config.control, source.sourceId,
    source.sourceRef?.type, source.sourceRef?.value,
    source.valueField, source.labelField,
  ]);
};

const resolved = (options: InputOption[]): ParamInputOptionsState =>
  options.length ? { status: 'success', options } : { status: 'error', options: [] };

export const createParamInputOptionsLoader = (api: OptionsApi) => {
  let generation = 0;
  let currentKey: string | undefined;
  let currentLoad: ParamInputOptionsLoad | undefined;

  const load = (config?: InputControlConfig): ParamInputOptionsLoad => {
    const key = getParamInputConfigKey(config);
    if (key === currentKey && currentLoad) return currentLoad;
    currentKey = key;
    const requestGeneration = ++generation;

    if (!config || config.control === 'input') {
      const initial: ParamInputOptionsState = { status: 'idle', options: [] };
      currentLoad = { sync: true, initial, promise: Promise.resolve(initial) };
      return currentLoad;
    }
    if (config.optionsSource.type === 'static') {
      const initial = resolved(config.optionsSource.staticItems);
      currentLoad = { sync: true, initial, promise: Promise.resolve(initial) };
      return currentLoad;
    }

    const source = config.optionsSource;
    const initial: ParamInputOptionsState = { status: 'loading', options: [] };
    const promise = (async (): Promise<ParamInputOptionsState | null> => {
      try {
        const response = source.sourceRef
          ? await api.getDataSourceList({ page_size: -1 })
          : [];
        const sourceItems = Array.isArray(response)
          ? response
          : extractDataSourceItems(response);
        if (requestGeneration !== generation) return null;
        const sourceId = resolveDynamicSourceId(source, sourceItems as Array<{ id: number; rest_api?: string }>);
        if (!sourceId) return requestGeneration === generation ? { status: 'error', options: [] } : null;
        const data = await api.getSourceDataByApiId(sourceId, {});
        const options = mapDynamicItems(
          extractDataSourceItems(data), source.valueField, source.labelField,
        );
        return requestGeneration === generation ? resolved(options) : null;
      } catch {
        return requestGeneration === generation ? { status: 'error', options: [] } : null;
      }
    })();
    currentLoad = { sync: false, initial, promise };
    return currentLoad;
  };

  return { load };
};
