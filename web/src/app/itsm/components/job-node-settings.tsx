'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Button, Select } from 'antd';
import { useItsmApi, type WorkflowJobOptions } from '../api/useItsmApi';
import type { FormFieldSchema } from '../types';
import { subformColumns } from './subform-columns';

function tableFields(fields: FormFieldSchema[]): FormFieldSchema[] {
  return fields.flatMap(field => field.type === 'table' ? [field] : tableFields(field.children || []));
}

export function JobNodeSettings({ config, fields, onChange }: {
  config: Record<string, unknown>;
  fields: FormFieldSchema[];
  onChange: (config: Record<string, unknown>) => void;
}) {
  const { ready, listJobOptions } = useItsmApi();
  const [options, setOptions] = useState<WorkflowJobOptions>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    listJobOptions().then(result => {
      if (active) setOptions(result);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : '无法加载作业和执行目标');
    });
    return () => { active = false; };
  }, [ready, listJobOptions, attempt]);

  const tables = tableFields(fields);
  const table = tables.find(item => item.key === config.table_key);
  const columns = table ? subformColumns(table).map(({ key, label }) => ({ value: key, label })) : [];
  const script = options?.scripts.find(item => item.id === config.script_id);
  const params = (config.params || {}) as Record<string, string>;
  const common = { showSearch: true, optionFilterProp: 'label' };
  return <>
    {error && <Alert type="error" message={error} action={<Button size="small" onClick={() => { setError(''); setAttempt(value => value + 1); }}>重新加载</Button>} />}
    <span className="text-xs">已有作业</span>
    <Select {...common} aria-label="已有作业" placeholder="选择作业平台脚本" value={config.script_id as number | undefined}
      loading={!options && !error} options={options?.scripts.map(({ id, name }) => ({ value: id, label: name }))}
      onChange={script_id => onChange({ ...config, script_id, params: {} })} />
    <span className="text-xs">执行目标</span>
    <Select {...common} aria-label="执行目标" placeholder="选择目标主机" value={config.target_id as number | undefined}
      loading={!options && !error} options={options?.targets.map(({ id, name }) => ({ value: id, label: name }))}
      onChange={target_id => onChange({ ...config, target_id })} />
    <span className="text-xs">逐行执行的子表单</span>
    <Select {...common} aria-label="逐行执行的子表单" placeholder="选择子表单" value={config.table_key as string | undefined}
      options={tables.map(({ key, label }) => ({ value: key, label }))} onChange={table_key => onChange({ ...config, table_key, params: {} })} />
    {script?.params.map(param => <React.Fragment key={param.name}>
      <span className="text-xs">{param.is_required && <span className="text-[var(--color-fail)]">* </span>}{param.label || param.name}</span>
      <Select {...common} aria-label={`参数 ${param.name}`} allowClear disabled={!table} placeholder="选择同行字段"
        value={params[param.name]} options={columns} onChange={value => {
          const next = { ...params };
          if (value) next[param.name] = value;
          else delete next[param.name];
          onChange({ ...config, params: next });
        }} />
    </React.Fragment>)}
  </>;
}
