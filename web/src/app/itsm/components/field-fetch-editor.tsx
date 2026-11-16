'use client';
import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Input, Modal, Select } from 'antd';
import { useItsmApi } from '../api/useItsmApi';
import { FieldFetchGuide } from './field-fetch-guide';
import { FieldParameterBindings, type ParameterSchema } from './field-parameter-bindings';
import { compatiblePaths, listPath, sampleAt, samplePaths, type SamplePath } from './field-fetch-mapping';
import type { FieldFetchBinding, FormFieldSchema } from '../types';
interface Capability { sources: string[]; mode: FieldFetchBinding['mode'] | null; shape: string | null; fill: boolean }
interface Catalog {
  capabilities?: Record<string, Capability>;
  gateways?: { path: string; method: string; name: string; request_schema?: ParameterSchema }[];
  integrations: { id: number; name: string; kind: string; transport?: string; request_schema?: ParameterSchema }[];
  tables: { key: string; name: string; columns?: { key: string; type: string }[] }[];
  dictionaries: { key: string; name: string }[];
}
function JsonInput({ label, value, onChange }: { label: string; value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [error, setError] = useState(false);
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setText(JSON.stringify(value, null, 2)); }, [value]);
  return <label className="flex flex-col gap-1 text-xs">{label}<Input.TextArea aria-label={label} rows={3} value={text} onFocus={() => { editing.current = true; }} onBlur={() => { editing.current = false; }} status={error ? 'error' : undefined} onChange={e => {
    setText(e.target.value);
    try { const next = JSON.parse(e.target.value); if (!next || Array.isArray(next) || typeof next !== 'object') throw Error(); setError(false); onChange(next); } catch { setError(true); }
  }} />{error && <span className="text-red-500">请输入 JSON 对象，当前内容尚未保存</span>}</label>;
}

interface EditorProps { field: FormFieldSchema; fields: FormFieldSchema[]; patch: (key: string, next: Partial<FormFieldSchema>) => void }
export function FieldFetchEditor({ field, fields, patch }: EditorProps) {
  const api = useItsmApi();
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<FormFieldSchema>();
  useEffect(() => { if (api.ready) void api.fieldCatalog().then(result => setCatalog(result as Catalog)).catch(() => setError('加载来源失败，请检查表单编辑权限')); }, [api.ready, api.fieldCatalog, field.fetch?.integration_id]);
  useEffect(() => { setDraft(undefined); }, [field.key]);
  const capability = catalog?.capabilities?.[field.type];
  const cfg = field.fetch;
  const source = cfg?.source === 'integration' ? cfg.integration_kind || catalog?.integrations.find(i => i.id === cfg.integration_id)?.kind || 'api' : cfg?.source || 'static';
  const title = capability?.mode === 'options' ? '选项来源' : capability?.mode === 'table' ? '行数据来源' : '自动填值';
  if (!capability) return error ? <Alert type="error" message={error} /> : null;
  if (!capability.sources.length || (cfg && (!capability.sources.includes(source) || cfg.mode !== capability.mode))) return cfg ? <Alert type="warning" message="此字段不支持当前取数配置" action={<Button onClick={() => patch(field.key, { fetch: undefined })}>移除无效配置</Button>} /> : null;
  const resource = cfg?.source === 'integration' ? catalog?.integrations.find(i => i.id === cfg.integration_id)?.name : (cfg?.source === 'dictionary' ? catalog?.dictionaries : catalog?.tables)?.find(i => i.key === cfg?.resource_key)?.name;
  const replaceDraft = (items: FormFieldSchema[]): FormFieldSchema[] => items.map(item => item.key === field.key ? draft! : item.children ? { ...item, children: replaceDraft(item.children) } : item);
  return <div className="flex flex-col gap-3">
    <span className="text-xs font-medium">{title}</span>
    <Select aria-label={title} value={source} options={[{ value: 'static', label: capability.mode === 'options' ? '自定义' : '手动填写' }, { value: 'api', label: 'API' }, { value: 'python', label: 'Python 动作' }, { value: 'dictionary', label: '数据字典' }, { value: 'table', label: '数据表' }].filter(i => i.value === 'static' || capability.sources.includes(i.value))} onChange={value => {
      if (value === 'static') { patch(field.key, { fetch: undefined }); return; }
      setDraft({ ...structuredClone(field), fetch: { source: ['api', 'python'].includes(value) ? 'integration' : value, integration_kind: ['api', 'python'].includes(value) ? value : undefined, mode: capability.mode, trigger: 'change', inputs: value === 'python' ? { rows: [], params: {} } : {}, label_path: value === 'dictionary' ? 'label' : '', value_path: value === 'dictionary' ? 'value' : '' } as FieldFetchBinding });
    }} />
    {cfg && <><span className="truncate text-xs text-[var(--color-text-3)]" title={resource}>{resource || '尚未选择资源'}</span><Button onClick={() => setDraft(structuredClone(field))}>设置</Button></>}
    {!cfg && capability.mode === 'options' && <Input.TextArea aria-label="自定义选项" rows={3} placeholder={'选项1:1\n选项2:2'} value={(field.source?.options || []).map(i => `${i.label}:${i.value}`).join('\n')} onChange={e => patch(field.key, { source: { type: 'static', options: e.target.value.split('\n').filter(Boolean).map(line => { const [label, value] = line.split(':'); return { label, value: value || label }; }) } })} />}
    {draft && <Modal title={capability.mode === 'options' ? '设置选项' : capability.mode === 'table' ? '设置行数据' : '设置自动填值'} open={!!draft} width={1000} centered destroyOnHidden maskClosable={false} okText="确定" cancelText="取消" styles={{ body: { maxHeight: '70vh', overflowY: 'auto', padding: '16px 4px' } }} onCancel={() => setDraft(undefined)} onOk={() => { if (draft) { patch(field.key, { fetch: draft.fetch, source: draft.source }); setDraft(undefined); } }}>
      {draft && <FieldFetchSettings key={draft.key} field={draft} fields={replaceDraft(fields)} patch={(_, next) => setDraft(current => current ? { ...current, ...next } : current)} />}
    </Modal>}
  </div>;
}

export function FieldFetchSettings({ field, fields, patch }: { field: FormFieldSchema; fields: FormFieldSchema[]; patch: (key: string, next: Partial<FormFieldSchema>) => void }) {
  const api = useItsmApi();
  const [catalog, setCatalog] = useState<Catalog>({ integrations: [], tables: [], dictionaries: [] });
  const [error, setError] = useState('');
  const [testValues, setTestValues] = useState<Record<string, unknown>>({});
  const [sample, setSample] = useState<{ data: unknown }>();
  const [output, setOutput] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  const request = useRef(0);
  const cfg = field.fetch;
  useEffect(() => { if (api.ready) void api.fieldCatalog().then(result => setCatalog(result as Catalog)).catch(() => setError('加载来源失败，请检查表单编辑权限')); }, [api.ready, api.fieldCatalog]);
  useEffect(() => () => { request.current++; }, []);
  const reset = () => { request.current++; setSample(undefined); setOutput(undefined); setError(''); setBusy(false); };
  const update = (next: Partial<FieldFetchBinding>) => { request.current++; setBusy(false); setOutput(undefined); setError(''); patch(field.key, { fetch: { ...cfg!, ...next } }); };
  const capability = catalog.capabilities?.[field.type];
  const choices = capability?.mode === 'options';
  const isTable = capability?.mode === 'table';
  const title = choices ? '选项来源' : isTable ? '行数据来源' : '自动填值';
  const kind = cfg?.integration_kind || catalog.integrations.find(item => item.id === cfg?.integration_id)?.kind || 'api';
  const python = cfg?.source === 'integration' && kind === 'python';
  const dictionary = cfg?.source === 'dictionary';
  const directTable = cfg?.source === 'table' && !cfg.transform_id;
  const tableColumns = catalog.tables.find(t => t.key === cfg?.resource_key)?.columns || [];
  const apiSchema = !python && cfg?.source === 'integration' ? catalog.integrations.find(i => i.id === cfg.integration_id)?.request_schema : undefined;
  const simpleProperties = Object.fromEntries(Object.entries(apiSchema?.properties || {}).filter(([, value]) => !['array', 'object'].includes(value.type || '')));
  const simpleSchema = apiSchema ? { ...apiSchema, properties: simpleProperties } : undefined;
  const dependencyFields = fields.filter(f => f.key !== field.key && f.state !== 'hidden');
  const sourceValue = cfg?.source === 'integration' ? kind : cfg?.source || 'static';
  const row = (label: string, child: React.ReactNode) => <label key={label} className="flex flex-col gap-1 text-xs">{label}{child}</label>;
  const sourceOptions = [{ value: 'static', label: choices ? '自定义' : '手动填写' }, { value: 'api', label: 'API' }, { value: 'python', label: 'Python 动作' }, { value: 'dictionary', label: '数据字典' }, { value: 'table', label: '数据表' }].filter(i => i.value === 'static' || capability?.sources.includes(i.value));
  const targetColumns = String(field.props?.columns || '').split('\n').filter(line => line.includes(':')).map(line => { const [label, key, type] = line.split(':').map(v => v.trim()); return { label, key, type: type === 'number' ? 'number' : 'string' }; });
  const paths = sample ? samplePaths(sample.data) : [];
  const chosenList = cfg?.transform_id ? '' : cfg?.list_path || (sample ? listPath(sample.data) : undefined);
  const sampleList = sample ? sampleAt(sample.data, chosenList || '') : undefined;
  const rowPaths = Array.isArray(sampleList) && sampleList.length ? samplePaths(sampleList[0]) : [];
  const columnPaths: SamplePath[] = tableColumns.map(c => ({ value: c.key, label: `${c.key} · ${c.type}`, type: ['number', 'integer', 'float'].includes(c.type) ? 'number' : c.type }));
  const optionsFor = (type: string) => compatiblePaths(directTable ? columnPaths : rowPaths.filter(p => capability?.shape !== 'tree' || !p.value.startsWith('children.')), type);
  const mappingSelect = (label: string, value: string | undefined, options: SamplePath[], change: (v: string) => void) => row(label,
    <Select aria-label={label} showSearch optionFilterProp="label" allowClear value={value === '' && options.some(o => o.value === '') ? '' : value || undefined} placeholder={sample || directTable ? '搜索并选择返回字段' : '先测试，再选择返回字段'}
      options={value && !options.some(o => o.value === value) ? [{ value, label: `${value}（当前配置）` }, ...options] : options}
      onChange={v => change(v || '')} />);
  if (!capability) return error ? <Alert type="error" message={error} /> : null;
  if (!capability.sources.length || (cfg && (!capability.sources.includes(sourceValue) || cfg.mode !== capability.mode))) return cfg ? <Alert type="warning" message="此字段不支持当前取数配置" action={<Button onClick={() => patch(field.key, { fetch: undefined })}>移除无效配置</Button>} /> : null;

  const test = async (inspect: boolean) => {
    const seq = ++request.current;
    setBusy(true); setError(''); setOutput(undefined);
    try {
      const result = await api.fetchField({ preview: true, inspect, schema: { version: 1, fields }, field: field.key, values: testValues }) as Record<string, unknown>;
      if (seq !== request.current) return;
      if (!inspect) { setOutput(Object.fromEntries(Object.entries(result).filter(([key]) => key !== 'receipt'))); return; }
      const data = result.sample;
      setSample({ data });
      const next: Partial<FieldFetchBinding> = {};
      const path = cfg!.transform_id ? '' : listPath(data);
      const rows = sampleAt(data, path || '');
      const leaves = Array.isArray(rows) && rows.length ? samplePaths(rows[0]) : [];
      if (cfg!.mode !== 'value' && !cfg!.list_path && path !== undefined && !cfg!.transform_id && cfg!.source === 'integration') next.list_path = path;
      if (choices) {
        if (!cfg!.label_path) next.label_path = ['label', 'name', 'title', 'text'].find(k => leaves.some(p => p.value === k && p.type === 'string'));
        if (!cfg!.value_path) next.value_path = ['value', 'id', 'key'].find(k => leaves.some(p => p.value === k && ['number', 'string'].includes(p.type)));
      } else if (isTable) {
        next.columns = { ...cfg!.columns };
        for (const c of targetColumns) if (!next.columns[c.key] && leaves.some(p => p.value === c.key && p.type === c.type)) next.columns[c.key] = c.key;
      } else if (!cfg!.value_path) {
        const candidates = compatiblePaths(samplePaths(data), field.type === 'number' ? 'number' : 'string');
        if (candidates.length === 1) next.value_path = candidates[0].value;
      }
      update(next);
    } catch (e) { if (seq === request.current) setError(e instanceof Error ? e.message : '测试失败'); }
    finally { if (seq === request.current) setBusy(false); }
  };
  return <div className="flex flex-col gap-3">
    <span className="text-xs font-medium">{title}</span>
    <Select aria-label={title} showSearch optionFilterProp="label" value={sourceValue} options={sourceOptions} onChange={source => {
      reset(); patch(field.key, { fetch: source === 'static' ? undefined : { source: ['api', 'python'].includes(source) ? 'integration' : source, integration_kind: ['api', 'python'].includes(source) ? source : undefined, mode: capability.mode, trigger: 'change', inputs: source === 'python' ? { rows: [], params: {} } : {}, label_path: source === 'dictionary' ? 'label' : '', value_path: source === 'dictionary' ? 'value' : '' } as FieldFetchBinding, source: { type: 'static', options: field.source?.options || [] } });
    }} />
    {!cfg && choices && <Input.TextArea aria-label="自定义选项" rows={3} placeholder={'选项1:1\n选项2:2'} value={(field.source?.options || []).map(i => `${i.label}:${i.value}`).join('\n')} onChange={e => patch(field.key, { source: { type: 'static', options: e.target.value.split('\n').filter(Boolean).map(line => { const [label, value] = line.split(':'); return { label, value: value || label }; }) } })} />}
    {cfg && <>
      <FieldFetchGuide mode={cfg.mode} source={python ? 'python' : cfg.source} number={field.type === 'number'} tree={capability.shape === 'tree'} fill={capability.fill} />
      {cfg.source === 'integration' ? row(python ? 'Python 动作' : 'API', <Select aria-label={python ? 'Python 动作' : 'API'} showSearch optionFilterProp="label" placeholder="搜索并选择" value={cfg.integration_id} options={[
        ...catalog.integrations.filter(i => i.kind === kind).map(i => ({ value: i.id, label: python ? i.name : `${i.transport === 'external' ? '外部 API' : '已配置'} · ${i.name}` })),
        ...(!python ? (catalog.gateways || []).map(g => ({ value: `gateway:${g.method}:${g.path}`, label: `网关 · ${g.name} · ${g.method} ${g.path}` })) : []),
      ]} onChange={async value => {
        reset();
        const seq = request.current;
        let integration_id = value as number;
        if (typeof value === 'string') {
          const gateway = catalog.gateways?.find(g => `gateway:${g.method}:${g.path}` === value);
          if (!gateway) return;
          setBusy(true);
          try {
            const item = await api.bindFieldGateway({ path: gateway.path, method: gateway.method }) as Catalog['integrations'][number];
            if (seq !== request.current) return;
            setCatalog(current => ({ ...current, integrations: [...current.integrations.filter(i => i.id !== item.id), item] }));
            integration_id = item.id;
          } catch (e) { if (seq === request.current) { setError(e instanceof Error ? e.message : '选择网关接口失败'); setBusy(false); } return; }
        }
        update({ integration_id, inputs: python ? { rows: [], params: {} } : {}, list_path: '', label_path: '', value_path: '', columns: {}, fill: {}, transform_id: undefined });
      }} />)
      : row(dictionary ? '数据字典' : '数据表', <Select aria-label={dictionary ? '数据字典' : '数据表'} showSearch optionFilterProp="label" placeholder="搜索并选择" value={cfg.resource_key} options={(dictionary ? catalog.dictionaries : catalog.tables).map(i => ({ value: i.key, label: i.name }))} onChange={resource_key => { reset(); update({ resource_key, inputs: {}, list_path: '', label_path: dictionary ? 'label' : '', value_path: dictionary ? 'value' : '', columns: {}, fill: {}, transform_id: undefined }); }} />)}
      {cfg.source === 'integration' && !python && <div className="flex items-center justify-between gap-3 text-xs text-[var(--color-text-3)]"><span>可直接搜索平台网关查询接口；外部 API 需先在集成中配置并启用，仅 GET 接口可用于字段取数。</span><a href="/itsm/form/integrations" target="_blank" rel="noreferrer" className="shrink-0 text-[var(--color-primary)]">配置外部 API</a></div>}
      {apiSchema && Object.keys(simpleProperties).length > 0 && <details open={apiSchema.required?.some(k => k in simpleProperties) || undefined}><summary className="cursor-pointer text-xs">接口参数</summary><div className="mt-2"><FieldParameterBindings tableLayout schema={simpleSchema} value={Object.fromEntries(Object.entries(cfg.inputs || {}).filter(([k]) => k in simpleProperties))} fields={dependencyFields} onChange={inputs => { reset(); update({ inputs: { ...Object.fromEntries(Object.entries(cfg.inputs || {}).filter(([k]) => !(k in simpleProperties))), ...inputs } }); }} /></div></details>}
      {directTable && <details><summary className="cursor-pointer text-xs">筛选条件</summary><div className="mt-2"><FieldParameterBindings tableLayout columns={tableColumns} value={cfg.inputs || {}} fields={dependencyFields} onChange={inputs => { reset(); update({ inputs }); }} /></div></details>}
      <Button loading={busy} disabled={cfg.source === 'integration' ? !cfg.integration_id : !cfg.resource_key} onClick={() => void test(true)}>测试并选择返回字段</Button>
      {sample && <span role="status" className="text-xs text-[var(--color-text-3)]">已获取样本，请确认下方映射；最多展示 3 行。</span>}
      {sample && Array.isArray(sampleList) && sampleList.length === 0 && <Alert type="info" message={directTable ? '暂无样本数据，可按数据表列配置，或调整筛选条件重试。' : '返回列表为空，请调整参数重试；已知字段路径可在高级设置中填写。'} />}
      {!dictionary && <div className="grid grid-cols-1 gap-4 rounded border border-[var(--color-border)] p-4 md:grid-cols-3">
        <span className="text-sm font-medium md:col-span-3">{choices ? '选项映射' : isTable ? '列映射' : '填入本字段'}</span>
        {cfg.mode !== 'value' && cfg.source === 'integration' && !cfg.transform_id && mappingSelect('返回列表', cfg.list_path, paths.filter(p => p.type === 'array'), list_path => update({ list_path, label_path: '', value_path: '', columns: {} }))}
        {choices && <>{mappingSelect('显示名称', cfg.label_path, optionsFor('string'), label_path => update({ label_path }))}{mappingSelect('选项值', cfg.value_path, optionsFor('scalar'), value_path => update({ value_path }))}</>}
        {cfg.mode === 'value' && mappingSelect('填充值', cfg.transform_id ? cfg.value_path : [cfg.list_path, cfg.value_path].filter(Boolean).join('.'), directTable ? compatiblePaths(columnPaths, field.type === 'number' ? 'number' : 'string').map(p => ({ ...p, value: `0.${p.value}` })) : compatiblePaths(paths, field.type === 'number' ? 'number' : 'string'), value_path => update(cfg.transform_id ? { value_path } : { list_path: '', value_path }))}
        {isTable && (targetColumns.length ? targetColumns.map(c => mappingSelect(`列：${c.label}`, cfg.columns?.[c.key], optionsFor(c.type), path => { const columns = { ...cfg.columns }; if (path) columns[c.key] = path; else delete columns[c.key]; update({ columns }); })) : <span className="text-xs">请先定义表格列，再选择返回字段。</span>)}
        {capability.shape === 'tree' && <span className="text-xs text-[var(--color-text-3)]">子节点使用返回数据中的 children。</span>}
      </div>}
      {capability.fill && <details><summary className="cursor-pointer text-xs">选中后填充其他字段</summary><div className="mt-2 flex flex-col gap-2">
        {Object.entries(cfg.fill || {}).map(([target, path]) => <div key={target} className="flex flex-col gap-2 rounded border border-[var(--color-border)] p-2"><Select aria-label="填充目标字段" showSearch optionFilterProp="label" value={target} options={dependencyFields.filter(f => ['input', 'textarea', 'number'].includes(f.type) && !['readonly', 'disabled'].includes(f.state || '')).map(f => ({ value: f.key, label: f.label }))} onChange={key => { const fill = { ...cfg.fill }; delete fill[target]; fill[key] = ''; update({ fill }); }} />{mappingSelect('填充值来源', path, optionsFor(dependencyFields.find(f => f.key === target)?.type === 'number' ? 'number' : 'string'), value => update({ fill: { ...cfg.fill, [target]: value } }))}<Button onClick={() => { const fill = { ...cfg.fill }; delete fill[target]; update({ fill }); }}>删除填充</Button></div>)}
        <Button onClick={() => { const f = dependencyFields.find(f => ['input', 'textarea', 'number'].includes(f.type) && !['readonly', 'disabled'].includes(f.state || '') && !(f.key in (cfg.fill || {}))); if (f) update({ fill: { ...cfg.fill, [f.key]: 'value' } }); }}>添加填充</Button>
      </div></details>}
      {cfg.mode !== 'options' && <Checkbox checked={!cfg.enforce} onChange={e => update({ enforce: !e.target.checked })}>允许手动修改</Checkbox>}
      <Button disabled={busy} onClick={() => void test(false)}>验证映射</Button>
      {output && <Alert type="success" showIcon message={choices ? `映射成功，返回 ${(output.options as unknown[])?.length || 0} 个选项` : isTable ? `映射成功，返回 ${(output.value as unknown[])?.length || 0} 行` : `填充值：${String(output.value)}`} />}
      {error && <Alert type="error" showIcon message={error} />}
      <details className="rounded border border-[var(--color-border)] p-2"><summary className="cursor-pointer text-xs font-medium">高级设置</summary><div className="mt-3 flex flex-col gap-3">
        <FieldFetchGuide mode={cfg.mode} advanced />
        {python && row('输入行数据', <Select aria-label="输入行数据" showSearch optionFilterProp="label" value={typeof cfg.inputs?.rows === 'string' ? cfg.inputs.rows : ''} options={[{ value: '', label: '空数据，仅使用参数' }, ...dependencyFields.filter(f => ['table', 'nestedTable'].includes(f.type)).map(f => ({ value: '${form.' + f.key + '}', label: f.label }))]} onChange={rows => { reset(); update({ inputs: { ...cfg.inputs, rows: rows || [] } }); }} />)}
        {python && <FieldParameterBindings tableLayout value={(cfg.inputs?.params as Record<string, unknown>) || {}} fields={dependencyFields} onChange={params => { reset(); update({ inputs: { ...cfg.inputs, rows: cfg.inputs?.rows || [], params } }); }} />}
        {!dictionary && <JsonInput key={`${sourceValue}:${cfg.integration_id}:${cfg.resource_key}`} label="完整输入参数（JSON）" value={cfg.inputs || {}} onChange={inputs => { reset(); update({ inputs }); }} />}
        {!dictionary && <>
          {row('手动列表路径', <Input aria-label="手动列表路径" value={cfg.list_path} onChange={e => { setSample(undefined); update({ list_path: e.target.value }); }} />)}
          {row('手动取值路径', <Input aria-label="手动取值路径" value={cfg.value_path} onChange={e => update({ value_path: e.target.value })} />)}
          {choices && row('手动名称路径', <Input aria-label="手动名称路径" value={cfg.label_path} onChange={e => update({ label_path: e.target.value })} />)}
        </>}
        {isTable && <JsonInput key={`${sourceValue}:columns`} label="手动列映射（JSON）" value={cfg.columns || {}} onChange={columns => update({ columns: columns as Record<string, string> })} />}
        {row('结果加工', <Select aria-label="结果加工" showSearch optionFilterProp="label" allowClear value={cfg.transform_id} options={catalog.integrations.filter(i => i.kind === 'python').map(i => ({ value: i.id, label: i.name }))} onChange={transform_id => { reset(); update({ transform_id }); }} />)}
        {cfg.transform_id && <FieldParameterBindings tableLayout value={cfg.transform_params || {}} fields={dependencyFields} onChange={transform_params => { reset(); update({ transform_params }); }} />}
        {row('取数时机', <Select aria-label="取数时机" value={cfg.trigger || 'change'} options={[{ value: 'change', label: '首次加载及依赖变化' }, { value: 'manual', label: '手动刷新' }]} onChange={trigger => update({ trigger })} />)}
        <JsonInput label="测试表单值（JSON）" value={testValues} onChange={value => { reset(); setTestValues(value); }} />
        {(sample || output) && <pre className="max-h-56 overflow-auto rounded bg-[var(--color-fill-1)] p-2 text-xs">{JSON.stringify(output || sample?.data, null, 2)}</pre>}
      </div></details>
    </>}
  </div>;
}
