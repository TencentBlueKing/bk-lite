import type { InputControlConfig, InputOption } from '@/app/ops-analysis/types/dataSource';
import type { SourceDataRequestOptions } from '@/app/ops-analysis/api/dataSource';
import type { SourceDataResult } from '@/app/ops-analysis/utils/sourceDataResponse';
import { getRequestErrorMessage } from '@/app/ops-analysis/utils/requestError';
import {
  classifyOptionSource,
  extractDataSourceItems,
  isOptionInputControl,
  mapDynamicItems,
} from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  canonicalQueryParams,
  stableStringify,
} from '@/app/ops-analysis/utils/optionsQueryParamRefs';

export type ParamInputOptionsState =
  | { status: 'idle'; options: [] }
  | { status: 'loading'; options: [] }
  | { status: 'success'; options: InputOption[] }
  | { status: 'blocked'; options: [] }
  | { status: 'error'; options: []; errorMessage?: string };

export interface ParamInputOptionsRequest {
  resolvedParams?: Record<string, unknown>;
  blocked?: boolean;
  blockReason?: 'empty' | 'invalid';
}

export interface ParamInputOptionsLoad {
  sync: boolean;
  initial: ParamInputOptionsState;
  promise: Promise<ParamInputOptionsState | null>;
}

export interface ParamInputOptionsLoaderOptions {
  suppressErrorNotification?: boolean;
  fallbackErrorMessage?: string;
  knownDataSources?: Array<{ id: number; name?: string; rest_api?: string }>;
}

const readHttpStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  if ('status' in error && typeof (error as { status?: unknown }).status === 'number') {
    return (error as { status: number }).status;
  }
  const response = (error as { response?: { status?: unknown } }).response;
  if (response && typeof response.status === 'number') return response.status;
  return undefined;
};

const identityErrorMessage = (status: string | undefined): string => (
  status === 'ambiguous'
    ? 'option-source-ambiguous'
    : status === 'forbidden'
      ? 'option-source-forbidden'
      : 'option-source-missing'
);

interface OptionsApi {
  getDataSourceList: (params?: unknown) => Promise<unknown>;
  getSourceDataByApiId: (
    id: number,
    params?: unknown,
    options?: SourceDataRequestOptions,
  ) => Promise<SourceDataResult>;
  resolveOptionSource?: (body: {
    sourceId?: number;
    builtinKey?: string;
    sourceRef?: string;
  }) => Promise<{ status?: string; id?: number }>;
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
  if (!isOptionInputControl(config)) return config.control;
  const source = config.optionsSource;
  if (source.type === 'static') {
    return JSON.stringify(['static', config.control, source.staticItems.map(typedOption)]);
  }
  return JSON.stringify([
    'dynamic', config.control, source.sourceId, source.builtinKey,
    source.sourceRef?.type, source.sourceRef?.value,
    source.valueField, source.labelField,
    canonicalQueryParams(source.queryParams),
  ]);
};

export const buildOptionsLoadSignature = (
  config: InputControlConfig | undefined,
  request?: ParamInputOptionsRequest,
): string => {
  if (request?.blocked) {
    return `${getParamInputConfigKey(config)}|blocked:${request.blockReason ?? 'empty'}`;
  }
  return `${getParamInputConfigKey(config)}|${stableStringify(request?.resolvedParams ?? {})}`;
};

const resolved = (options: InputOption[]): ParamInputOptionsState =>
  options.length ? { status: 'success', options } : { status: 'error', options: [] };

const OPTION_PAGE_CAP = 200;

const asRecord = (value: unknown): Record<string, unknown> | undefined => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
);

const finiteNumber = (value: unknown): number | undefined => (
  typeof value === 'number' && Number.isFinite(value) ? value : undefined
);

/**
 * 只有响应同时带 page、page_size、count，且 count 大于本页条数时才继续翻页。
 * 旧的数组选项源没有这些字段，仍只取第一次结果。
 */
const readOptionPage = (data: unknown): {
  items: Record<string, unknown>[];
  page?: number;
  pageSize?: number;
  count?: number;
} => {
  const items = extractDataSourceItems(data);
  const record = asRecord(data);
  if (!record) return { items };
  return {
    items,
    page: finiteNumber(record.page),
    pageSize: finiteNumber(record.page_size),
    count: finiteNumber(record.count),
  };
};

export const localizeOptionLoadError = (
  message: string | undefined,
  t: (key: string) => string,
): string | undefined => {
  if (message === 'option page limit exceeded') return t('dashboard.optionPageLimitExceeded');
  if (message === 'option page ended before count') return t('dashboard.optionPageEndedEarly');
  return message;
};

export const createParamInputOptionsLoader = (
  api: OptionsApi,
  getLoaderOptions?: () => ParamInputOptionsLoaderOptions | undefined,
) => {
  let generation = 0;
  let currentKey: string | undefined;
  let currentLoad: ParamInputOptionsLoad | undefined;
  let settled = false;

  const load = (
    config?: InputControlConfig,
    request?: ParamInputOptionsRequest,
  ): ParamInputOptionsLoad => {
    const key = buildOptionsLoadSignature(config, request);
    if (key === currentKey && currentLoad) return currentLoad;
    currentKey = key;
    settled = false;
    const requestGeneration = ++generation;

    if (!isOptionInputControl(config)) {
      const initial: ParamInputOptionsState = { status: 'idle', options: [] };
      settled = true;
      currentLoad = { sync: true, initial, promise: Promise.resolve(initial) };
      return currentLoad;
    }
    if (config.optionsSource.type === 'static') {
      const initial = resolved(config.optionsSource.staticItems);
      settled = true;
      currentLoad = { sync: true, initial, promise: Promise.resolve(initial) };
      return currentLoad;
    }

    const source = config.optionsSource;
    if (request?.blocked) {
      const initial: ParamInputOptionsState = { status: 'blocked', options: [] };
      settled = true;
      currentLoad = { sync: true, initial, promise: Promise.resolve(initial) };
      return currentLoad;
    }
    const resolvedParams = request?.resolvedParams ?? {};
    const initial: ParamInputOptionsState = { status: 'loading', options: [] };
    const promise = (async (): Promise<ParamInputOptionsState | null> => {
      const loaderOptions = getLoaderOptions?.();
      const requestOptions: SourceDataRequestOptions | undefined =
        loaderOptions?.suppressErrorNotification
          ? { suppressErrorNotification: true }
          : undefined;
      const fallbackErrorMessage = loaderOptions?.fallbackErrorMessage ?? '';
      try {
        const knownItems = loaderOptions?.knownDataSources ?? [];
        let sourceId = typeof source.sourceId === 'number' ? source.sourceId : undefined;
        let resolverUnavailable = !api.resolveOptionSource;
        let resolvedThroughIdentity = false;
        if (api.resolveOptionSource) {
          try {
            const identity = await api.resolveOptionSource({
              sourceId,
              builtinKey: source.builtinKey,
              sourceRef: source.sourceRef?.value,
            });
            if (requestGeneration !== generation) return null;
            if (identity.status !== 'resolved' || typeof identity.id !== 'number') {
              settled = true;
              return {
                status: 'error',
                options: [],
                errorMessage: identityErrorMessage(identity.status),
              };
            }
            sourceId = identity.id;
            resolvedThroughIdentity = true;
          } catch (error) {
            if (requestGeneration !== generation) return null;
            if (error instanceof Error && error.message === 'option-source-resolver-unavailable') {
              resolverUnavailable = true;
            } else {
              settled = true;
              const errorMessage = getRequestErrorMessage(error, '') || 'option-source-unavailable';
              return { status: 'error', options: [], errorMessage };
            }
          }
        }
        if (resolverUnavailable && sourceId === undefined && source.sourceRef) {
          const namedInKnown = source.sourceRef.value.includes('::')
            ? classifyOptionSource(source, knownItems)
            : undefined;
          if (namedInKnown?.status === 'resolved') sourceId = namedInKnown.id;
        }
        if (resolverUnavailable && sourceId === undefined && source.sourceRef) {
          const response = await api.getDataSourceList({ page_size: -1 });
          const sourceItems = Array.isArray(response)
            ? response
            : extractDataSourceItems(response);
          if (requestGeneration !== generation) return null;
          const classified = classifyOptionSource(
            source,
            sourceItems as Array<{ id: number; name?: string; rest_api?: string; build_in_key?: string | null }>,
          );
          if (classified.status === 'resolved') sourceId = classified.id;
          else {
            settled = true;
            return {
              status: 'error',
              options: [],
              errorMessage: classified.status === 'ambiguous'
                ? 'option-source-ambiguous'
                : 'option-source-missing',
            };
          }
        }
        if (sourceId === undefined) {
          if (requestGeneration !== generation) return null;
          settled = true;
          return { status: 'error', options: [], errorMessage: 'option-source-missing' };
        }
        // 解析过的来源由控件自己显示缺失/无权，不再弹一条全局提示。
        const dataRequestOptions: SourceDataRequestOptions | undefined = resolvedThroughIdentity
          ? { ...requestOptions, suppressErrorNotification: true }
          : requestOptions;
        const { data } = await api.getSourceDataByApiId(sourceId, resolvedParams, dataRequestOptions);
        const firstPage = readOptionPage(data);
        const items = [...firstPage.items];
        const shouldPage = firstPage.page !== undefined
          && firstPage.pageSize !== undefined
          && firstPage.count !== undefined
          && firstPage.count > items.length;
        if (shouldPage) {
          let nextPage = firstPage.page! + 1;
          let pages = 1;
          while (items.length < firstPage.count!) {
            if (pages >= OPTION_PAGE_CAP) {
              throw new Error('option page limit exceeded');
            }
            const next = await api.getSourceDataByApiId(
              sourceId,
              { ...resolvedParams, page: nextPage, page_size: firstPage.pageSize },
              dataRequestOptions,
            );
            if (requestGeneration !== generation) return null;
            const nextItems = readOptionPage(next.data).items;
            if (!nextItems.length) {
              throw new Error('option page ended before count');
            }
            items.push(...nextItems);
            nextPage += 1;
            pages += 1;
          }
        }
        const options = mapDynamicItems(
          items, source.valueField, source.labelField,
        );
        if (requestGeneration !== generation) return null;
        settled = true;
        return resolved(options);
      } catch (error) {
        if (requestGeneration !== generation) return null;
        settled = true;
        const httpStatus = readHttpStatus(error);
        if (httpStatus === 403 || httpStatus === 404) {
          return {
            status: 'error',
            options: [],
            errorMessage: httpStatus === 403
              ? 'option-source-forbidden'
              : 'option-source-missing',
          };
        }
        const errorMessage = getRequestErrorMessage(error, fallbackErrorMessage) || 'option-source-unavailable';
        return {
          status: 'error',
          options: [],
          errorMessage,
        };
      }
    })();
    currentLoad = { sync: false, initial, promise };
    return currentLoad;
  };

  const reset = () => {
    generation += 1;
    currentKey = undefined;
    currentLoad = undefined;
    settled = false;
  };

  /**
   * 同一配置的请求还在飞时保留它。已经落地的缓存（例如上一块画布）丢掉。
   */
  const dropSettledCache = (key: string) => {
    if (currentKey === key && currentLoad && !settled) return;
    reset();
  };

  return { load, reset, dropSettledCache };
};
