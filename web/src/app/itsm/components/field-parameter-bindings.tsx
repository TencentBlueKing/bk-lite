'use client';
import { Button, Input, InputNumber, Select } from 'antd';
import type { FormFieldSchema } from '../types';
export interface ParameterSchema { properties?: Record<string, { type?: string; title?: string; description?: string; default?: unknown; enum?: (string | number)[] }>; required?: string[] }
export function FieldParameterBindings({ value, fields, onChange, schema, columns, tableLayout = false }: { tableLayout?: boolean; schema?: ParameterSchema; columns?: { key: string; type: string }[]; value: Record<string, unknown>; fields: FormFieldSchema[]; onChange: (value: Record<string, unknown>) => void }) {
  const options = fields.flatMap(function flatten(field): { value: string; label: string }[] { return field.state === 'hidden' ? [] : [{ value: field.key, label: `${field.label} (${field.key})` }, ...(field.children || []).flatMap(flatten)]; });
  return <div className="flex flex-col gap-2">
    {tableLayout && <div className="hidden grid-cols-[minmax(120px,1fr)_60px_80px_minmax(100px,1fr)_minmax(240px,2fr)] gap-3 bg-[var(--color-fill-1)] p-3 text-xs font-medium md:grid"><span>参数</span><span>必填</span><span>类型</span><span>描述</span><span>参数值</span></div>}
    {Object.entries({ ...Object.fromEntries(Object.keys(schema?.properties || {}).map(key => [key, schema?.properties?.[key].default])), ...value }).map(([key, item], index) => {
      const definition: NonNullable<ParameterSchema['properties']>[string] | undefined = schema?.properties?.[key] || columns?.find(column => column.key === key);
      const rename = (name: string) => { if (name && name !== key && !(name in value)) onChange(Object.fromEntries(Object.entries(value).map(([k, v]) => [k === key ? name : k, v]))); };
      const match = typeof item === 'string' ? item.match(/^\$\{(form|user|query)\.(\w+)\}$/) : null;
      const kind = match?.[1] || 'constant';
      const set = (next: unknown) => onChange({ ...value, [key]: next });
      return <div key={key} className={tableLayout ? "grid grid-cols-1 items-start gap-3 border-b border-[var(--color-border)] p-3 md:grid-cols-[minmax(120px,1fr)_60px_80px_minmax(100px,1fr)_minmax(240px,2fr)]" : "flex flex-col gap-2 rounded border border-[var(--color-border)] p-2"}>
        <div className="flex items-center gap-1">{schema ? <span className="flex-1 text-xs">{key}{!tableLayout && ` · ${definition?.type || '未知参数'}`}{!tableLayout && schema.required?.includes(key) && <span className="text-red-500"> *</span>}</span>
        : columns ? <Select aria-label={`参数${index + 1}名称`} showSearch optionFilterProp="label" value={key} options={columns.map(column => ({ value: column.key, label: column.key }))} onChange={rename} />
        : <Input aria-label={`参数${index + 1}名称`} defaultValue={key} placeholder="参数名" onBlur={e => rename(e.target.value.trim())} />}
          <Button disabled={schema?.required?.includes(key)} aria-label={schema ? `重置参数${index + 1}` : `删除参数${index + 1}`} onClick={() => onChange(Object.fromEntries(Object.entries(value).filter(([k]) => k !== key)))}>{schema ? '重置' : '删除'}</Button></div>
        {tableLayout && <><span className="text-xs">{schema?.required?.includes(key) ? '是' : '否'}</span><span className="text-xs">{definition?.type || '—'}</span><span className="text-xs text-[var(--color-text-3)]">{definition?.description || '—'}</span></>}
        {!tableLayout && definition?.description && <span className="text-xs text-[var(--color-text-3)]">{definition.description}</span>}
        <div className="flex min-w-0 flex-col gap-2"><Select aria-label={`参数${index + 1}值来源`} value={kind} options={[{ value: 'constant', label: '固定值' }, { value: 'form', label: '表单字段' }, { value: 'user', label: '当前用户 / 组织' }, { value: 'query', label: '搜索 / 分页' }]} onChange={next => set(next === 'constant' ? '' : '${' + next + '.' + (({ form: options[0]?.value || '', user: 'username', query: 'keyword' } as Record<string, string>)[next]) + '}')} />
        <span className="text-xs text-[var(--color-text-3)]">{kind === 'form' ? '选择其他表单字段作为参数，用户修改该字段时可重新取数。测试时请在高级设置中填写对应的测试表单值。' : kind === 'user' ? '运行时使用当前登录用户或组织，无需手动填写账号。' : kind === 'query' ? '绑定字段搜索词或分页值。只有当前字段提供搜索或分页交互时才会变化。' : '固定值每次请求都相同，例如页码填 1、每页条数填 20。参数名称和类型以接口或脚本要求为准。'}</span>
        {kind === 'constant' && definition?.enum ? <Select aria-label={`参数${index + 1}固定值`} value={item as string | number} options={definition.enum.map(v => ({ value: v, label: String(v) }))} onChange={set} />
        : kind === 'constant' && ['integer', 'number'].includes(definition?.type || '') ? <InputNumber aria-label={`参数${index + 1}固定值`} value={item as number} precision={definition?.type === 'integer' ? 0 : undefined} onChange={set} />
        : kind === 'constant' && definition?.type === 'boolean' ? <Select aria-label={`参数${index + 1}固定值`} value={item == null ? undefined : String(item)} options={[{ value: 'true', label: '是' }, { value: 'false', label: '否' }]} onChange={v => set(v === 'true')} />
        : kind === 'constant' ? <Input aria-label={`参数${index + 1}固定值`} value={typeof item === 'string' ? item : JSON.stringify(item)} onChange={e => { try { set(definition?.type === 'string' ? e.target.value : JSON.parse(e.target.value)); } catch { set(e.target.value); } }} />
        : <Select aria-label={`参数${index + 1}联动字段`} showSearch optionFilterProp="label" placeholder="搜索并选择" value={match?.[2]} options={kind === 'form' ? options : kind === 'user' ? [{ value: 'username', label: '当前用户' }, { value: 'teams', label: '当前组织' }, { value: 'domain', label: '当前域' }] : [{ value: 'keyword', label: '搜索关键词' }, { value: 'page', label: '页码' }, { value: 'page_size', label: '每页条数' }]} onChange={name => set('${' + kind + '.' + name + '}')} />}
        </div>
      </div>;
    })}
    {!schema && <Button size="small" disabled={!!columns && columns.every(column => column.key in value)} onClick={() => { if (columns) { const next = columns.find(column => !(column.key in value)); if (next) onChange({ ...value, [next.key]: '' }); return; } let n = 1; while (`param_${n}` in value) n++; onChange({ ...value, [`param_${n}`]: '' }); }}>{columns ? "添加筛选条件" : "添加参数"}</Button>}
  </div>;
}
