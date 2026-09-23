import { ActionConfig } from '@/app/alarm/types/settings';

export type ParamBinding = ActionConfig['param_bindings'][number];

export interface ScriptParam {
  name: string;
  label?: string;
  default?: string;
}

/** 变量下拉中的触发事件类型；执行时取 ActionExecution.trigger_event。 */
export const TRIGGER_EVENT_FIELD = 'trigger_event';

const MASKED_DEFAULTS = new Set(['******', '***']);

export function plainScriptDefault(param: ScriptParam): string {
  const raw = param.default;
  if (raw == null || MASKED_DEFAULTS.has(String(raw))) return '';
  return String(raw);
}

export function defaultBindingsFromScript(params: ScriptParam[]): ParamBinding[] {
  return params.map((param) => ({
    name: param.name,
    from: 'const',
    value: plainScriptDefault(param),
    allow_adjust: false,
  }));
}

export function alignParamBindings(
  params: ScriptParam[],
  existing: ParamBinding[] = [],
  options?: { reloadConstDefaults?: boolean }
): ParamBinding[] {
  const byName = new Map(existing.map((item) => [item.name, item]));
  return params.map((param) => {
    const prev = byName.get(param.name);
    if (!prev) {
      return {
        name: param.name,
        from: 'const',
        value: plainScriptDefault(param),
        allow_adjust: false,
      };
    }
    if (prev.from === 'field') {
      return {
        name: param.name,
        from: 'field',
        value: prev.value,
        allow_adjust: false,
      };
    }
    return {
      name: param.name,
      from: 'const',
      value: options?.reloadConstDefaults ? plainScriptDefault(param) : prev.value,
      allow_adjust: prev.allow_adjust === true,
    };
  });
}

export function adjustableConstBindings(bindings: ParamBinding[] = []): ParamBinding[] {
  return bindings.filter((item) => item.from === 'const' && item.allow_adjust === true);
}

export function fieldBindingsIncomplete(bindings: ParamBinding[] = []): boolean {
  return bindings.some((item) => item.from === 'field' && !String(item.value || '').trim());
}
