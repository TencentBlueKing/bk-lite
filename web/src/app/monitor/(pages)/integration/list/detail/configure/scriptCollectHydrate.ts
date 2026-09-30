import { DataMapper } from '@/app/monitor/hooks/integration/useDataMapper';
import {
  defaultScriptTimeoutSeconds,
  parseScriptDurationSeconds
} from './scriptCollectTimeout';

const WINDOWS_INTERPRETER_VALUES = new Set([
  'powershell.exe',
  'cmd.exe',
  'python.exe'
]);

const inferStoredScriptOs = (interpreter: unknown) =>
  WINDOWS_INTERPRETER_VALUES.has(String(interpreter || '')) ? 'windows' : 'linux';

const asScriptText = (value: unknown): string =>
  typeof value === 'string' ? value : '';

const firstBkliteScriptPlugin = (apiData: Record<string, unknown> | null | undefined) => {
  const child = apiData?.child as Record<string, unknown> | undefined;
  const content = child?.content as Record<string, unknown> | undefined;
  const document = content?._toml_document as Record<string, unknown> | undefined;
  const inputs = document?.inputs as Record<string, unknown> | undefined;
  const plugins = inputs?.bklite_script;
  return Array.isArray(plugins) ? (plugins[0] as Record<string, unknown> | undefined) : undefined;
};

/**
 * 从 CollectConfig child 取出脚本正文。
 * 优先 config.script；兼容旧 command / commands，以及 toml_to_dict 未铺到 config 时的 _toml_document。
 */
export const resolveScriptBodyFromChildConfig = (
  apiData: Record<string, unknown> | null | undefined
): string => {
  const child = apiData?.child as Record<string, unknown> | undefined;
  const content = child?.content as Record<string, unknown> | undefined;
  const config = (content?.config as Record<string, unknown> | undefined) || {};
  const fromConfig = asScriptText(config.script);
  if (fromConfig) return fromConfig;
  const fromCommand = asScriptText(config.command);
  if (fromCommand) return fromCommand;
  if (Array.isArray(config.commands)) {
    const joined = config.commands
      .filter((item: unknown) => typeof item === 'string')
      .join('\n');
    if (joined) return joined;
  }
  const plugin = firstBkliteScriptPlugin(apiData) || {};
  const fromDoc = asScriptText(plugin.script) || asScriptText(plugin.command);
  if (fromDoc) return fromDoc;
  if (Array.isArray(plugin.commands)) {
    return plugin.commands
      .filter((item: unknown) => typeof item === 'string')
      .join('\n');
  }
  return '';
};

const dropEmptyHydratedFields = (values: Record<string, unknown>) => {
  const next: Record<string, unknown> = {};
  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (typeof value === 'string' && !value) return;
    next[key] = value;
  });
  return next;
};

/** 把已落库 child CollectConfig 映回接入表单（脚本正文 + OS / 解释器 / run_as / interval 等）。 */
export const hydrateScriptCollectFormValues = (
  formFields: Array<{ name?: string; transform_on_edit?: unknown }> | undefined,
  apiData: Record<string, unknown> | null | undefined,
  _collectType?: unknown
): Record<string, unknown> => {
  if (!apiData) return {};
  const formValues: Record<string, unknown> = {};
  (formFields || []).forEach((field) => {
    const { name, transform_on_edit } = field || {};
    if (!name || !transform_on_edit) return;
    formValues[name] = DataMapper.transformValue(
      null,
      transform_on_edit,
      'toForm',
      apiData
    );
  });
  const script = resolveScriptBodyFromChildConfig(apiData);
  if (script) {
    formValues.script = script;
  }
  const child = apiData?.child as Record<string, unknown> | undefined;
  const content = child?.content as Record<string, unknown> | undefined;
  const config = (content?.config as Record<string, unknown> | undefined) || {};
  const plugin = firstBkliteScriptPlugin(apiData) || {};
  if (formValues.interpreter == null || formValues.interpreter === '') {
    const interpreter = config.interpreter || plugin.interpreter;
    if (interpreter) formValues.interpreter = interpreter;
  }
  if (formValues.run_as == null || formValues.run_as === '') {
    const runAs = config.run_as || plugin.run_as;
    if (runAs) formValues.run_as = runAs;
  }
  if (formValues.interval == null || formValues.interval === '') {
    const rawInterval = config.interval || plugin.interval;
    if (rawInterval != null) formValues.interval = rawInterval;
  }
  if (typeof formValues.interval === 'string') {
    const match = formValues.interval.match(/^(\d+)s$/);
    if (match) {
      formValues.interval = Number(match[1]);
    } else if (/^\d+$/.test(formValues.interval)) {
      formValues.interval = Number(formValues.interval);
    }
  }
  if (formValues.timeout == null || formValues.timeout === '') {
    const rawTimeout = config.timeout || plugin.timeout;
    if (rawTimeout != null) formValues.timeout = rawTimeout;
  }
  if (typeof formValues.timeout === 'string') {
    const match = formValues.timeout.match(/^(\d+)s$/);
    if (match) {
      formValues.timeout = Number(match[1]);
    } else if (/^\d+$/.test(formValues.timeout)) {
      formValues.timeout = Number(formValues.timeout);
    }
  }
  if (formValues.timeout == null || formValues.timeout === '') {
    const intervalSec = parseScriptDurationSeconds(formValues.interval);
    if (intervalSec != null) {
      formValues.timeout = defaultScriptTimeoutSeconds(intervalSec);
    }
  }
  if (!formValues.script_os) {
    formValues.script_os = inferStoredScriptOs(formValues.interpreter);
  }
  return dropEmptyHydratedFields(formValues);
};
