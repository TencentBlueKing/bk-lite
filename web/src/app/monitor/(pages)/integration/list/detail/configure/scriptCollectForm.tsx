'use client';

import React from 'react';
import { Alert, Form, Input, InputNumber, Segmented, Select } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CodeEditor from '@/components/code-editor';
import {
  SCRIPT_MIN_INTERVAL_SECONDS,
  defaultScriptTimeoutSeconds,
  parseScriptDurationSeconds,
  shouldEmitScriptTimeout
} from './scriptCollectTimeout';

export const LINUX_INTERPRETERS = [
  { label: '/bin/sh', value: '/bin/sh' },
  { label: '/bin/bash', value: '/bin/bash' },
  { label: '/usr/bin/python3', value: '/usr/bin/python3' }
];

export const WINDOWS_INTERPRETERS = [
  { label: 'powershell.exe', value: 'powershell.exe' },
  { label: 'cmd.exe', value: 'cmd.exe' },
  { label: 'python.exe', value: 'python.exe' }
];

const RESOURCE_KNOB_FIELDS = new Set([
  'cpu',
  'memory',
  'mem',
  'cpu_limit',
  'mem_limit',
  'memory_limit'
]);

const SCRIPT_TIMEOUT_FIELD = {
  name: 'timeout',
  label: '脚本超时（秒）',
  label_en: 'Script Timeout (seconds)',
  type: 'inputNumber',
  required: true,
  default_value: 59,
  description: '默认 = 间隔 − 1',
  description_en: 'Default = interval − 1',
  widget_props: {
    min: 1,
    precision: 0,
    placeholder: '超时',
    placeholder_en: 'Timeout',
    addonAfter: '秒'
  },
  transform_on_edit: {
    origin_path: 'child.content.config.timeout',
    to_form: { regex: '^(\\d+)s$' },
    to_api: { suffix: 's' }
  },
  script_collect: true
};

const SCRIPT_INTERVAL_TIMEOUT_WIDTH = 300;

export const isScriptCollectConfig = (
  config: { collect_type?: unknown; config_type?: unknown } | null | undefined
) => {
  if (!config) return false;
  if (String(config.collect_type || '') === 'script') return true;
  const types = config.config_type;
  if (Array.isArray(types)) return types.some((item) => String(item) === 'script');
  return String(types || '') === 'script';
};

export const interpretersForOs = (os: unknown) =>
  os === 'windows' ? WINDOWS_INTERPRETERS : LINUX_INTERPRETERS;

export const inferScriptOs = (interpreter: unknown) => {
  const value = String(interpreter || '');
  return WINDOWS_INTERPRETERS.some((item) => item.value === value) ? 'windows' : 'linux';
};

const isScriptCollectPayload = (
  values: Record<string, any> | null | undefined,
  collectType?: unknown
) => String(collectType || '') === 'script' || values?.script_os != null;

/**
 * Windows 提交/调试载荷完全省略 run_as（不写空串），由服务账号执行。
 * 解释器不在当前 OS 白名单内时，重置为该 OS 的默认项。
 */
export const applyScriptCollectSubmit = <T extends Record<string, any>>(
  values: T,
  collectType?: unknown
): T => {
  if (!values || !isScriptCollectPayload(values, collectType)) {
    return values;
  }
  const next: Record<string, any> = { ...values };
  const os = next.script_os;
  if (os === 'linux' || os === 'windows') {
    const allowed = interpretersForOs(os);
    const current = String(next.interpreter ?? '');
    if (!allowed.some((item) => item.value === current)) {
      next.interpreter = allowed[0].value;
    }
  }
  if (os === 'windows') {
    delete next.run_as;
  }
  return next as T;
};

/** 编辑保存沿用已落库配置时，Windows 必须删掉历史 run_as，避免空串再次下发。 */
export const omitPersistedWindowsRunAs = (
  result: { child?: { content?: { config?: Record<string, any> } } } | null | undefined,
  values: Record<string, any> | null | undefined
) => {
  if (values?.script_os !== 'windows') return;
  const config = result?.child?.content?.config;
  if (config && Object.prototype.hasOwnProperty.call(config, 'run_as')) {
    delete config.run_as;
  }
};

/** 默认 timeout（interval-1）不写入 child 配置，由采集器按间隔推导。 */
export const omitPersistedDefaultScriptTimeout = (
  result: { child?: { content?: { config?: Record<string, any> } } } | null | undefined,
  values: Record<string, any> | null | undefined,
  collectType?: unknown
) => {
  if (!isScriptCollectPayload(values, collectType)) return;
  const config = result?.child?.content?.config;
  if (!config) return;
  const interval = values?.interval ?? config.interval;
  const timeout = values?.timeout ?? config.timeout;
  if (!shouldEmitScriptTimeout(timeout, interval)) {
    delete config.timeout;
  }
};

export const normalizeScriptCollectFormFields = (fields: any[] = []) => {
  const kept = fields.filter(
    (field) => field?.name !== 'script_os' && !RESOURCE_KNOB_FIELDS.has(String(field?.name || ''))
  );
  const byName = new Map(kept.map((field) => [field.name, field]));
  const previousInterpreter = byName.get('interpreter') || {};
  const previousRunAs = byName.get('run_as') || {};
  const scriptOs = {
    name: 'script_os',
    label: '操作系统',
    label_en: 'Operating System',
    type: 'segmented',
    required: true,
    default_value: 'linux',
    description: '决定解释器白名单与执行用户。Windows 以服务账号运行。',
    options: [
      { label: 'Linux', value: 'linux' },
      { label: 'Windows', value: 'windows' }
    ],
    transform_on_edit: {
      origin_path: 'child.content.config.script_os',
      to_api: {}
    }
  };
  const interpreter = {
    ...previousInterpreter,
    name: 'interpreter',
    label: previousInterpreter.label || '解释器',
    label_en: previousInterpreter.label_en || 'Interpreter',
    type: 'select',
    required: true,
    default_value: previousInterpreter.default_value || '/bin/sh',
    description: '按操作系统从白名单选择解释器',
    options: LINUX_INTERPRETERS,
    options_by_os: {
      linux: LINUX_INTERPRETERS,
      windows: WINDOWS_INTERPRETERS
    },
    widget_props: {
      ...(previousInterpreter.widget_props || {}),
      placeholder: '选择解释器'
    },
    transform_on_edit: previousInterpreter.transform_on_edit || {
      origin_path: 'child.content.config.interpreter',
      to_api: {}
    }
  };
  const runAs = {
    ...previousRunAs,
    name: 'run_as',
    label: '执行用户',
    label_en: 'Run As',
    type: 'input',
    required: false,
    default_value: previousRunAs.default_value || 'telegraf',
    os_driven: true,
    rules: [],
    description: 'Linux 必填，且不能为 root 或 UID 0。',
    widget_props: {
      ...(previousRunAs.widget_props || {}),
      placeholder: 'telegraf'
    },
    transform_on_edit: previousRunAs.transform_on_edit || {
      origin_path: 'child.content.config.run_as',
      to_api: {}
    }
  };
  const rest = kept
    .filter(
      (field) =>
        field.name !== 'interpreter' &&
        field.name !== 'run_as' &&
        field.name !== 'timeout'
    )
    .map((field) => {
      if (field?.name !== 'script') return field;
      return {
        ...field,
        transform_on_edit: field.transform_on_edit || {
          origin_path: 'child.content.config.script',
          to_api: {}
        }
      };
    });
  const withTimeout: any[] = [];
  let insertedTimeout = false;
  rest.forEach((field) => {
    const nextField =
      field?.name === 'interval'
        ? { ...field, script_collect: true }
        : field;
    withTimeout.push(nextField);
    if (field?.name === 'interval') {
      withTimeout.push({
        ...SCRIPT_TIMEOUT_FIELD,
        ...(byName.get('timeout') || {}),
        ...SCRIPT_TIMEOUT_FIELD
      });
      insertedTimeout = true;
    }
  });
  if (!insertedTimeout) {
    withTimeout.push({ ...SCRIPT_TIMEOUT_FIELD });
  }
  return [scriptOs, interpreter, runAs, ...withTimeout];
};

const LINUX_RUN_AS_DEFAULT = 'telegraf';

export const ScriptIntervalTimeoutFields: React.FC<{
  intervalField?: Record<string, any>;
  timeoutField?: Record<string, any>;
  mode?: string;
}> = ({ intervalField, timeoutField, mode }) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const interval = Form.useWatch('interval');
  const timeout = Form.useWatch('timeout');
  const [clampHint, setClampHint] = React.useState<number | null>(null);
  const clampTimerRef = React.useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  );
  const prevIntervalRef = React.useRef<number | null>(null);
  const createTimeoutInitedRef = React.useRef(false);
  const intervalLocked =
    mode === 'edit' && intervalField?.editable === false;
  const timeoutLocked = mode === 'edit' && timeoutField?.editable === false;
  const intervalInitial =
    parseScriptDurationSeconds(intervalField?.default_value) ??
    SCRIPT_MIN_INTERVAL_SECONDS;
  const timeoutFromInterval = defaultScriptTimeoutSeconds(intervalInitial);
  const timeoutTemplateDefault = parseScriptDurationSeconds(
    timeoutField?.default_value
  );
  const timeoutInitial =
    timeoutTemplateDefault != null && timeoutTemplateDefault === timeoutFromInterval
      ? timeoutTemplateDefault
      : timeoutFromInterval;
  const intervalSeconds =
    parseScriptDurationSeconds(interval) ?? intervalInitial;
  const maxTimeout = defaultScriptTimeoutSeconds(
    intervalSeconds > 0 ? intervalSeconds : SCRIPT_MIN_INTERVAL_SECONDS
  );

  const showClampHint = React.useCallback((value: number) => {
    setClampHint(value);
    if (clampTimerRef.current !== undefined) {
      clearTimeout(clampTimerRef.current);
    }
    clampTimerRef.current = setTimeout(() => {
      setClampHint(null);
    }, 3000);
  }, []);

  const handleIntervalChange = (value: number | string | null) => {
    const newInterval = parseScriptDurationSeconds(value);
    if (newInterval == null || newInterval < 1) {
      return;
    }
    const formInterval = parseScriptDurationSeconds(form.getFieldValue('interval'));
    const oldInterval =
      formInterval != null && formInterval !== newInterval
        ? formInterval
        : prevIntervalRef.current;
    const timeoutSec = parseScriptDurationSeconds(form.getFieldValue('timeout'));
    const nextMax = defaultScriptTimeoutSeconds(newInterval);
    prevIntervalRef.current = newInterval;
    const wasDefault =
      timeoutSec == null ||
      timeoutSec <= 0 ||
      (oldInterval != null &&
        timeoutSec === defaultScriptTimeoutSeconds(oldInterval));
    if (wasDefault) {
      if (timeoutSec !== nextMax) {
        form.setFieldValue('timeout', nextMax);
      }
      return;
    }
    if (timeoutSec != null && timeoutSec > nextMax) {
      form.setFieldValue('timeout', nextMax);
      showClampHint(nextMax);
    }
  };

  React.useEffect(() => {
    const intervalSec = parseScriptDurationSeconds(interval);
    if (intervalSec == null || intervalSec < 1) {
      return;
    }
    prevIntervalRef.current = intervalSec;
    const nextMax = defaultScriptTimeoutSeconds(intervalSec);
    const timeoutSec = parseScriptDurationSeconds(timeout);
    if (timeoutSec == null || timeoutSec <= 0) {
      form.setFieldValue('timeout', nextMax);
      createTimeoutInitedRef.current = true;
      return;
    }
    if (timeoutSec > nextMax) {
      form.setFieldValue('timeout', nextMax);
      createTimeoutInitedRef.current = true;
      return;
    }
    if (
      !createTimeoutInitedRef.current &&
      mode !== 'edit'
    ) {
      const templateDefault =
        timeoutTemplateDefault ??
        defaultScriptTimeoutSeconds(SCRIPT_MIN_INTERVAL_SECONDS);
      if (timeoutSec === templateDefault && timeoutSec !== nextMax) {
        form.setFieldValue('timeout', nextMax);
      }
    }
    createTimeoutInitedRef.current = true;
  }, [form, interval, timeout, mode, timeoutTemplateDefault]);

  React.useEffect(
    () => () => {
      if (clampTimerRef.current !== undefined) {
        clearTimeout(clampTimerRef.current);
      }
    },
    []
  );

  return (
    <div className="mb-3 flex flex-wrap items-start gap-4">
      <Form.Item
        className="mb-0"
        name="interval"
        required
        label={intervalField?.label || t('monitor.integrations.interval', '采集间隔')}
        rules={[
          { required: true, message: t('common.required') },
          {
            validator: async (_, value) => {
              const seconds = parseScriptDurationSeconds(value);
              if (seconds == null) {
                return;
              }
              if (seconds < SCRIPT_MIN_INTERVAL_SECONDS) {
                throw new Error(
                  t(
                    'monitor.integrations.intervalMin60',
                    '采集间隔不能小于 60 秒'
                  )
                );
              }
            }
          }
        ]}
        initialValue={intervalField?.default_value ?? SCRIPT_MIN_INTERVAL_SECONDS}
      >
        <InputNumber
          min={SCRIPT_MIN_INTERVAL_SECONDS}
          precision={0}
          disabled={intervalLocked}
          addonAfter={intervalField?.widget_props?.addonAfter || 's'}
          placeholder={
            intervalField?.widget_props?.placeholder ||
            t('monitor.integrations.interval', '间隔')
          }
          className="align-middle"
          style={{ width: SCRIPT_INTERVAL_TIMEOUT_WIDTH }}
          onChange={handleIntervalChange}
        />
      </Form.Item>
      <div className="flex min-w-0 flex-col">
        <Form.Item
          className="mb-0"
          name="timeout"
          required
          label={
            timeoutField?.label ||
            t('monitor.integrations.scriptTimeout', '脚本超时（秒）')
          }
          rules={[
            { required: true, message: t('common.required') },
            {
              validator: async (_, value) => {
                const seconds = parseScriptDurationSeconds(value);
                if (seconds == null) {
                  return;
                }
                if (seconds < 1 || seconds > maxTimeout) {
                  throw new Error(
                    t(
                      'monitor.integrations.scriptTimeoutRange',
                      '脚本超时必须在 1 到 {max} 秒之间',
                      { max: maxTimeout }
                    )
                  );
                }
              }
            }
          ]}
          initialValue={timeoutInitial}
        >
          <InputNumber
            min={1}
            max={maxTimeout}
            precision={0}
            disabled={timeoutLocked}
            addonAfter={t('monitor.integrations.scriptTimeoutUnit', '秒')}
            placeholder={
              timeoutField?.widget_props?.placeholder ||
              t('monitor.integrations.scriptTimeout', '超时')
            }
            className="align-middle"
            style={{ width: SCRIPT_INTERVAL_TIMEOUT_WIDTH }}
          />
        </Form.Item>
        <div className="mt-1 min-h-[18px] text-[12px] leading-[18px]">
          {clampHint != null ? (
            <span className="text-[var(--color-warning)]">
              {t(
                'monitor.integrations.scriptTimeoutClamped',
                '已按新间隔调整为 {value} 秒',
                { value: clampHint }
              )}
            </span>
          ) : (
            <span className="text-[var(--color-text-3)]">
              {t(
                'monitor.integrations.scriptTimeoutHelper',
                '默认 = 间隔 − 1，最大 {max} 秒',
                { max: maxTimeout }
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * 先写入 run_as，再改 script_os。
 * 依赖校验会在 script_os 变更时抓当前值；若之后才补默认值，异步校验仍会用空串报「不能为空」。
 */
export const syncScriptRunAsForOs = (form: FormInstance, os: string) => {
  if (os === 'windows') {
    form.setFields([{ name: 'run_as', value: '', errors: [] }]);
  } else {
    const current = String(form.getFieldValue('run_as') || '').trim();
    if (!current) {
      form.setFields([{ name: 'run_as', value: LINUX_RUN_AS_DEFAULT, errors: [] }]);
    } else {
      form.setFields([{ name: 'run_as', errors: [] }]);
    }
  }
  void Promise.resolve().then(() => {
    form.validateFields(['run_as']).catch(() => undefined);
  });
};

export const ScriptOsSegmented: React.FC<{
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  options?: { label: string; value: string }[];
}> = ({ value, onChange, disabled, options }) => {
  const form = Form.useFormInstance();
  return (
    <Segmented
      disabled={disabled}
      value={value}
      options={options || [
        { label: 'Linux', value: 'linux' },
        { label: 'Windows', value: 'windows' }
      ]}
      onChange={(next) => {
        const os = String(next);
        syncScriptRunAsForOs(form, os);
        onChange?.(os);
        const interpreters = interpretersForOs(os);
        const current = String(form.getFieldValue('interpreter') || '');
        if (!interpreters.some((item) => item.value === current)) {
          form.setFieldValue('interpreter', interpreters[0].value);
        }
      }}
    />
  );
};

export const ScriptInterpreterSelect: React.FC<{
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  style?: React.CSSProperties;
  placeholder?: string;
}> = ({ value, onChange, disabled, style, placeholder }) => {
  const form = Form.useFormInstance();
  const os = Form.useWatch('script_os');
  const list = interpretersForOs(os);
  const allowed = !value || list.some((item) => item.value === value);
  const fallback = list[0]?.value;
  const osReady = os === 'linux' || os === 'windows';
  let displayValue = value;
  if (!allowed) {
    displayValue = osReady ? fallback : undefined;
  }
  React.useEffect(() => {
    if (!osReady || !value || allowed || !fallback) return;
    form.setFieldValue('interpreter', fallback);
  }, [allowed, fallback, form, osReady, value]);
  return (
    <Select
      showSearch
      optionFilterProp="label"
      disabled={disabled}
      style={style}
      value={displayValue}
      options={list}
      placeholder={placeholder || '选择解释器'}
      onChange={onChange}
    />
  );
};

export const ScriptWindowsRunAsBanner: React.FC = () => {
  const { t } = useTranslation();
  const os = Form.useWatch('script_os');
  if (os !== 'windows') return null;
  return (
    <Alert
      message={t(
        'monitor.integrations.runAsWindowsHelper',
        'Windows 以服务账号运行，执行用户不可修改'
      )}
      type="info"
      showIcon={false}
      className="mb-2 max-w-[640px] !border-[var(--color-border-2)] !bg-[var(--color-fill-2)] !text-[var(--color-text-1)] text-xs"
    />
  );
};

export const ScriptRunAsInput: React.FC<{
  value?: string;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  disabled?: boolean;
  style?: React.CSSProperties;
  placeholder?: string;
}> = ({ value, onChange, disabled, style, placeholder }) => {
  const os = Form.useWatch('script_os');
  const windows = os === 'windows';
  return (
    <Input
      disabled={Boolean(disabled || windows)}
      style={style}
      value={windows ? '' : value}
      placeholder={windows ? '服务账号' : placeholder || 'telegraf'}
      onChange={windows ? undefined : onChange}
    />
  );
};

export const ScriptBodyEditor: React.FC<{
  value?: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  height?: string;
}> = ({ value, onChange, readOnly, placeholder, height }) => {
  const os = Form.useWatch('script_os');
  return (
    <div style={{ maxWidth: 640 }} className="w-full">
      <CodeEditor
        mode={os === 'windows' ? 'powershell' : 'sh'}
        theme="monokai"
        height={height || '200px'}
        width="100%"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        headerOptions={{ copy: true, fullscreen: true }}
        readOnly={Boolean(readOnly)}
      />
    </div>
  );
};
