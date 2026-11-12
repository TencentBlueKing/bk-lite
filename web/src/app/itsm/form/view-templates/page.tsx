'use client';

import { Button, Input, Select, message } from 'antd';
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

  return (
    <div className="flex flex-col gap-3">
      <div className="text-base font-semibold leading-tight text-[var(--color-text-1)]">视图模板</div>
      <div className="flex flex-wrap gap-2">
        <Select
          className="w-48"
          placeholder="表单"
          value={formId}
          options={forms.map((item) => ({ value: item.id, label: item.name }))}
          onChange={(value) => setFormId(value)}
        />
        <Input className="w-40" placeholder="模板名" value={name} onChange={(event) => setName(event.target.value)} />
        <Input className="w-56" placeholder="字段顺序，逗号分隔" value={fields} onChange={(event) => setFields(event.target.value)} />
        <Input className="w-32" placeholder="匹配状态" value={matchStatus} onChange={(event) => setMatchStatus(event.target.value)} />
        <Button
          type="primary"
          onClick={() => {
            if (!formId || !name.trim()) {
              return;
            }
            void api.createViewTemplate({
              form_id: formId,
              name: name.trim(),
              layout: { fields: fields.split(',').map((item) => item.trim()).filter(Boolean) },
              match_rules: matchStatus.trim() ? { status: matchStatus.trim() } : {},
            }).then(() => {
              setName('');
              return load();
            });
          }}
        >
          新建
        </Button>
      </div>
      {items.map((item) => (
        <div key={item.id} className="text-sm">
          {item.name} · 表单 {item.form_id} · {(item.layout?.fields || []).join(', ') || '未指定顺序'}
        </div>
      ))}
    </div>
  );
}
