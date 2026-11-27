'use client';

import { App, Button, Empty, Input, List, Modal, Popconfirm, Space, Tag } from 'antd';
import type { FormInstance } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../api/useItsmApi';
import type { FormFieldSchema } from '../types';

interface SavedTemplate {
  id: number;
  name: string;
  form_data: Record<string, unknown>;
  changed: boolean;
}

function formKeys(fields: FormFieldSchema[]): string[] {
  return fields.flatMap(field => field.type === 'section' || field.type === 'tab' ? formKeys(field.children || []) : [field.key]);
}

export function TicketFormTemplates({ serviceId, form, fields, disabled }: {
  serviceId: number;
  form: FormInstance;
  fields: FormFieldSchema[];
  disabled?: boolean;
}) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [items, setItems] = useState<SavedTemplate[]>([]);
  const [open, setOpen] = useState<'save' | 'choose' | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const data = await api.listFormTemplates(serviceId);
    setItems(data.items);
  }, [api.listFormTemplates, serviceId]);

  useEffect(() => {
    if (!open || !api.ready) return;
    void load().catch(cause => setError(cause instanceof Error ? cause.message : '加载模板失败'));
  }, [open, api.ready, load]);

  const save = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      await api.saveFormTemplate(serviceId, { name: name.trim(), form_data: form.getFieldsValue(true) });
      message.success('模板已保存，动态选项、附件和签名下次提单时需重新填写');
      setName('');
      setOpen(null);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '保存模板失败');
    } finally { setBusy(false); }
  };

  const apply = (item: SavedTemplate) => {
    const blank = Object.fromEntries(formKeys(fields).map(key => [key, undefined]));
    form.setFieldsValue({ ...blank, _field_receipts: undefined, ...item.form_data });
    setOpen(null);
    message.info(item.changed ? '已套用可用字段；旧字段已跳过，动态选项、附件和签名请重新填写' : '模板已套用；动态选项、附件和签名请重新填写');
  };

  const remove = async (item: SavedTemplate) => {
    try {
      await api.deleteFormTemplate(serviceId, item.id);
      setItems(current => current.filter(value => value.id !== item.id));
      message.success('模板已删除');
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : '删除模板失败');
    }
  };

  return <>
    <Button disabled={disabled} onClick={() => { setError(''); setOpen('choose'); }}>套用模板</Button>
    <Button disabled={disabled} onClick={() => { setError(''); setOpen('save'); }}>保存为模板</Button>
    <Modal title="保存提单模板" open={open === 'save'} okText="保存模板" okButtonProps={{ disabled: !name.trim(), loading: busy }} onOk={() => void save()} onCancel={() => setOpen(null)}>
      <p className="text-sm text-[var(--color-text-3)]">保存当前已填写的普通字段，供同一流程再次提单使用。动态取数选项、附件和签名需要重新填写。</p>
      <Input aria-label="模板名称" maxLength={100} showCount placeholder="输入模板名称" value={name} onChange={event => setName(event.target.value)} onPressEnter={() => void save()} />
    </Modal>
    <Modal title="套用提单模板" open={open === 'choose'} footer={null} onCancel={() => setOpen(null)}>
      <p className="text-sm text-[var(--color-text-3)]">选择后会替换当前填写的字段。动态取数选项、附件和签名需要重新填写。</p>
      {error ? <div role="alert" className="mb-3 text-red-500">{error} <Button size="small" onClick={() => void load()}>重试</Button></div> : null}
      <List dataSource={items} locale={{ emptyText: <Empty description="当前流程暂无提单模板" /> }} renderItem={item => <List.Item actions={[
        <Button key="apply" type="link" onClick={() => apply(item)}>套用</Button>,
        <Popconfirm key="delete" title="删除这份模板？" onConfirm={() => void remove(item)}><Button danger type="link">删除</Button></Popconfirm>,
      ]}><Space><span>{item.name}</span>{item.changed ? <Tag color="warning">部分字段已变化</Tag> : null}</Space></List.Item>} />
    </Modal>
  </>;
}
