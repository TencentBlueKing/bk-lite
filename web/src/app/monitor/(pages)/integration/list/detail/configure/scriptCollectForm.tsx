'use client';

import React from 'react';
import { Alert, Form, Input, Segmented, Select } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import CodeEditor from '@/components/code-editor';

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
  'timeout',
  'cpu',
  'memory',
  'mem',
  'cpu_limit',
  'mem_limit',
  'memory_limit'
]);

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
    .filter((field) => field.name !== 'interpreter' && field.name !== 'run_as')
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
  return [scriptOs, interpreter, runAs, ...rest];
};

const LINUX_RUN_AS_DEFAULT = 'telegraf';

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
