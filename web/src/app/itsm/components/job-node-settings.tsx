'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Button, Input, InputNumber, Select } from 'antd';
import { useItsmApi, type WorkflowJobOptions } from '../api/useItsmApi';
import type { FormFieldSchema } from '../types';
import { subformColumns } from './subform-columns';
import { jobBindings, jobFormFields, jobMode, type Binding, type BindingSource, type Option } from './job-node-config';

const tableTypes = new Set(['table', 'nestedTable', 'task', 'cab']);
const collectionTypes = new Set([...tableTypes, 'checkbox', 'multiselect', 'user', 'group', 'attachment', 'multiUser',
  'multiCascade', 'userGroup', 'multiUserGroup', 'dateRange', 'multiCmdb', 'associateConfig', 'subProcessForm']);
const sources: Option[] = [
  { value: 'item', label: '当前项' }, { value: 'form', label: '表单字段' }, { value: 'system', label: '系统变量' },
  { value: 'output', label: '上游输出' }, { value: 'literal', label: '固定值' },
];
const systemOptions = [
  { value: 'id', label: '工单 ID' }, { value: 'sn', label: '工单号' }, { value: 'title', label: '工单标题' }, { value: 'creator', label: '提单人' },
];
export function JobNodeSettings({ config, fields, outputs = [], onChange }: {
  config: Record<string, unknown>;
  fields: FormFieldSchema[];
  outputs?: Option[];
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

  const form = jobFormFields(fields);
  const fieldOptions = form.filter(field => !collectionTypes.has(field.type)).map(({ key, label }) => ({ value: key, label }));
  const mode = jobMode(config);
  const dispatchMode = config.dispatch_mode || (config.batch_size ? 'batch' : 'parallel');
  const collection = String(config.collection || (config.table_key ? `form.${config.table_key}` : ''));
  const selectedField = form.find(field => `form.${field.key}` === collection);
  const table = selectedField && tableTypes.has(selectedField.type) ? selectedField : undefined;
  const itemOptions = table
    ? subformColumns(table).filter(field => !collectionTypes.has(field.type)).map(field => ({ value: field.key, label: field.label }))
    : [{ value: '', label: '当前项整体' }];
  const variables = { item: itemOptions, form: fieldOptions, output: outputs, system: systemOptions };
  const params = jobBindings(config);
  const script = options?.scripts.find(item => item.id === config.script_id);
  const common = { showSearch: true, optionFilterProp: 'label' };
  function update(changes: Record<string, unknown>) {
    const next: Record<string, unknown> = { ...config, mode, ...(collection && { collection }), params, ...changes };
    delete next.table_key;
    if (!next.batch_size || next.mode === 'once') delete next.batch_size;
    if (next.mode === 'once') { delete next.collection; delete next.dispatch_mode; }
    if (next.dispatch_mode === 'parallel') delete next.batch_size;
    onChange(next);
  }
  function bind(name: string, binding?: Binding) {
    const next = { ...params };
    if (binding) next[name] = binding;
    else delete next[name];
    update({ params: next });
  }
  const stableParams = Object.fromEntries(Object.entries(params).filter(([, binding]) => binding.source !== 'item'));
  return <>
    {error && <Alert type="error" message={error} action={<Button size="small" onClick={() => { setError(''); setAttempt(value => value + 1); }}>重新加载</Button>} />}
    <span className="text-xs">已有作业</span>
    <Select {...common} aria-label="已有作业" placeholder="选择作业平台脚本" value={config.script_id as number | undefined}
      loading={!options && !error} options={options?.scripts.map(({ id, name }) => ({ value: id, label: name }))}
      onChange={script_id => update({ script_id, params: {} })} />
    <span className="text-xs">执行目标</span>
    <Select {...common} aria-label="执行目标" placeholder="选择目标主机" value={config.target_id as number | undefined}
      loading={!options && !error} options={options?.targets.map(({ id, name }) => ({ value: id, label: name }))}
      onChange={target_id => update({ target_id })} />
    <span className="text-xs">执行方式</span>
    <Select aria-label="执行方式" value={mode} options={[{ value: 'once', label: '单次执行' }, { value: 'each', label: '逐项执行' }]}
      onChange={mode => update({ mode, params: stableParams })} />
    {mode === 'each' && <>
      <span className="text-xs">执行集合</span>
      <Select {...common} aria-label="执行集合" placeholder="选择集合字段或上游输出" value={collection || undefined}
        options={[
          { label: '表单字段', options: form.filter(field => collectionTypes.has(field.type)).map(field => ({ value: `form.${field.key}`, label: field.label })) },
          { label: '上游输出', options: outputs.map(option => ({ ...option, value: `output.${option.value}` })) },
        ]}
        onChange={collection => update({ collection, params: stableParams })} />
      <span className="text-xs">调度方式</span>
      <Select aria-label="调度方式" value={dispatchMode} options={[{ value: 'parallel', label: '并发执行全部项' }, { value: 'batch', label: '分批执行' }]}
        onChange={dispatch_mode => update({ dispatch_mode, ...(dispatch_mode === 'batch' ? { batch_size: 1 } : {}) })} />
      {dispatchMode === 'batch' && <><span className="text-xs">每批项数</span>
      <InputNumber aria-label="每批项数" className="!w-full" min={1} max={100} precision={0} placeholder="可选，1 至 100"
        value={config.batch_size as number | undefined} onChange={batch_size => {
          if (batch_size == null || (Number.isInteger(batch_size) && batch_size >= 1 && batch_size <= 100)) update({ batch_size });
        }} /></>}
    </>}
    {script?.params.map(param => {
      const binding = params[param.name];
      const source = binding?.source;
      return <React.Fragment key={param.name}>
        <span className="text-xs">{param.is_required && <span className="text-[var(--color-fail)]">* </span>}{param.label || param.name}</span>
        <Select aria-label={`${param.name} 参数来源`} placeholder="选择参数来源" allowClear value={source}
          options={sources.filter(option => option.value !== 'item' || mode === 'each')}
          onChange={(source?: BindingSource) => bind(param.name, source ? { source, key: '' } : undefined)} />
        {source && (source === 'literal' || (source === 'item' && collection.startsWith('output.'))
          ? <Input aria-label={`参数 ${param.name}`} value={binding.key}
              placeholder={source === 'literal' ? '输入固定值' : '输入属性名，留空传入当前项整体'}
              onChange={event => bind(param.name, { source, key: event.target.value })} />
          : <Select {...common} aria-label={`参数 ${param.name}`} value={binding.key || (source === 'item' && !table ? '' : undefined)}
              placeholder="选择变量" options={variables[source]} onChange={key => bind(param.name, { source, key })} />)}
      </React.Fragment>;
    })}
  </>;
}
