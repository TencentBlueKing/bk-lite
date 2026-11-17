'use client';

import { Input, Select, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import ItsmListTable from '../../components/itsm-list-table';
import { ItsmListToolbar, ItsmCreateButton } from '../../components/list-controls';
import { FieldRow } from '../../components/field-row';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';

interface FormItem {
  id: number;
  name: string;
}

interface TemplateItem {
  id: number;
  form_id: number;
  name: string;
  layout: { fields?: string[] };
}

export default function ViewTemplatesPage() {
  const api = useItsmApi();
  const [open,setOpen] = useState(false);
  const [keyword,setKeyword] = useState('');
  const [saving,setSaving] = useState(false);
  const [forms, setForms] = useState<FormItem[]>([]);
  const [formId, setFormId] = useState<number | undefined>();
  const [items, setItems] = useState<TemplateItem[]>([]);
  const [name, setName] = useState('');
  const [fields, setFields] = useState('title');
  const [matchStatus, setMatchStatus] = useState('');

  const load = useCallback(async () => {
    const [formData, templateData] = await Promise.all([
      api.listForms() as Promise<{ items?: FormItem[] }>,
      api.listViewTemplates() as Promise<{ items?: TemplateItem[] }>,
    ]);
    const nextForms = formData.items || [];
    setForms(nextForms);
    setFormId((current) => current || nextForms[0]?.id);
    setItems(templateData.items || []);
  }, [api.listForms, api.listViewTemplates]);

  useEffect(() => {
    if (!api.ready) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : '加载失败'));
  }, [api.ready, load]);

  const save = async () => {
    if (!formId || !name.trim()) { message.warning('请选择表单并填写模板名称'); return; }
    setSaving(true);
    try {
      await api.createViewTemplate({ form_id: formId, name: name.trim(), layout: { fields: fields.split(',').map(item => item.trim()).filter(Boolean) }, match_rules: matchStatus.trim() ? {status: matchStatus.trim()} : {} });
      setOpen(false); setName(''); await load();
    } catch (error) { message.error(error instanceof Error ? error.message : '保存失败'); }
    finally { setSaving(false); }
  };
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar search={{value:keyword,onChange:setKeyword,placeholder:'搜索模板名称'}} actions={<ItsmCreateButton onClick={() => setOpen(true)} />} />
    <ItsmListTable queryKey={keyword} rowKey="id" dataSource={items.filter(item => item.name.toLowerCase().includes(keyword.trim().toLowerCase()))} columns={[
      {title:'名称',dataIndex:'name',key:'name'},
      {title:'表单',key:'form',render:(_,item:TemplateItem)=>forms.find(form=>form.id===item.form_id)?.name || item.form_id},
      {title:'字段顺序',key:'fields',render:(_,item:TemplateItem)=>(item.layout?.fields || []).join('、') || '未指定顺序'},
    ]} />
    <OperateModal title="新建视图模板" open={open} onCancel={() => setOpen(false)} onOk={() => void save()} confirmLoading={saving}>
      <div className="flex flex-col gap-4">
        <FieldRow label="表单"><Select className="w-full" showSearch optionFilterProp="label" value={formId} options={forms.map(item=>({value:item.id,label:item.name}))} onChange={setFormId} /></FieldRow>
        <FieldRow label="名称"><Input value={name} onChange={event=>setName(event.target.value)} /></FieldRow>
        <FieldRow label="字段顺序"><Input placeholder="字段标识，逗号分隔" value={fields} onChange={event=>setFields(event.target.value)} /></FieldRow>
        <FieldRow label="匹配状态"><Input value={matchStatus} onChange={event=>setMatchStatus(event.target.value)} /></FieldRow>
      </div>
    </OperateModal>
  </div>;
}
