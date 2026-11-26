'use client';

import { DeleteOutlined } from '@ant-design/icons';
import { Alert, App, Button, Checkbox, Input, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { useItsmApi } from '../../api/useItsmApi';
import { ItsmDrawer } from '../../components/interaction-surfaces';
import CustomTable from '../../components/itsm-list-table';
import { ItsmCreateButton, ItsmListToolbar, ItsmRowActions } from '../../components/list-controls';
import { ItsmListEntry } from '../../components/list-entry';
import type { SurveyQuestion, SurveyTemplateSnapshot } from '../../types';

interface Template extends SurveyTemplateSnapshot {
  id: number;
}

interface TemplateList {
  items: Template[];
  can_add?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
}

interface Editor extends SurveyTemplateSnapshot {
  id?: number;
}

export default function SurveyTemplatesPage() {
  const { message } = App.useApp();
  const api = useItsmApi();
  const [data, setData] = useState<TemplateList>({ items: [] });
  const [keyword, setKeyword] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState('');

  const load = useCallback(async () => {
    setLoadError('');
    try {
      setData(await api.listResources('surveys') as unknown as TemplateList);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '加载满意度模板失败');
    } finally {
      setLoaded(true);
    }
  }, [api.listResources]);

  useEffect(() => {
    if (api.ready) void load();
  }, [api.ready, load]);

  const open = (template?: Template) => {
    if (!template) {
      setEditor({ name: '', questions: [] });
      return;
    }
    const questions = Array.isArray(template.questions) ? template.questions
      .filter(question => typeof question?.id === 'string' && typeof question.title === 'string')
      .map(({ id, title, required }) => ({ id, title, required: required === true })) : [];
    setEditor({ id: template.id, name: template.name, questions });
  };
  const readOnly = editor?.id !== undefined && !data.can_edit;
  const updateQuestion = (id: string, values: Partial<SurveyQuestion>) => {
    setEditor(current => current && { ...current, questions: current.questions.map(question => question.id === id ? { ...question, ...values } : question) });
  };
  const save = async () => {
    if (!editor || readOnly) return;
    const payload = { name: editor.name.trim(), questions: editor.questions.map(question => ({ ...question, title: question.title.trim() })) };
    if (!payload.name || payload.questions.some(question => !question.title)) throw new Error('请填写模板名称和题目');
    if (editor.id === undefined) await api.createResource('surveys', payload);
    else await api.updateResource('surveys', editor.id, payload);
    setEditor(null);
    await load();
  };

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, placeholder: '搜索模板名称' }}
      actions={data.can_add && <ItsmCreateButton onClick={() => open()} />} />
    <p className="mb-3 mt-2 text-xs text-[var(--color-text-3)]">工单使用完结时的最新模板。评分和评价意见随问卷一同收集。</p>
    {loadError && <Alert className="mb-3" type="error" showIcon message={loadError} action={<Button onClick={() => void load()}>重试</Button>} />}
    <CustomTable<Template> rowKey="id" queryKey={keyword} loading={!loaded}
      dataSource={data.items.filter(template => template.name.toLowerCase().includes(keyword.trim().toLowerCase()))}
      columns={[
        { title: '模板名称', key: 'name', render: (_, template) => <ItsmListEntry onClick={() => open(template)}>{template.name}</ItsmListEntry> },
        { title: '自定义题数', key: 'count', render: (_, template) => Array.isArray(template.questions) ? template.questions.length : 0 },
        { title: '应用状态', key: 'active', render: (_, template) => template.id === data.items[0]?.id ? <Tag color="processing">当前模板</Tag> : '—' },
        { title: '操作', key: 'actions', width: 120, fixed: 'right', render: (_, template) => <ItsmRowActions items={[
          { key: 'edit', label: '编辑', kind: 'edit', hidden: !data.can_edit, onClick: () => open(template) },
          { key: 'delete', label: '删除', kind: 'delete', hidden: !data.can_delete, danger: true,
            confirm: { title: '删除满意度模板', content: template.name }, onClick: () => {
              void api.deleteResource('surveys', template.id).then(load)
                .catch(error => message.error(error instanceof Error ? error.message : '删除失败'));
            } },
        ]} /> },
      ]} />
    <ItsmDrawer open={Boolean(editor)} width={640} formValue={editor} onCancel={() => setEditor(null)}
      onOk={readOnly ? undefined : save} title={readOnly ? '查看满意度模板' : editor?.id ? '编辑满意度模板' : '新建满意度模板'}>
      {editor && <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-2">
          模板名称
          <Input value={editor.name} maxLength={128} disabled={readOnly}
            onChange={event => setEditor({ ...editor, name: event.target.value })} />
        </label>
        <div className="flex flex-col gap-3">
          {editor.questions.map((question, index) => <div key={question.id}
            className="flex flex-wrap items-center gap-3 rounded border border-[var(--color-border)] p-3">
            <label className="flex min-w-48 flex-1 flex-col gap-2">
              {`题目 ${index + 1}`}
              <Input value={question.title} maxLength={200} disabled={readOnly} onChange={event => updateQuestion(question.id, { title: event.target.value })} />
            </label>
            <Checkbox checked={question.required} disabled={readOnly} aria-label={`题目 ${index + 1} 必填`}
              onChange={event => updateQuestion(question.id, { required: event.target.checked })}>必填</Checkbox>
            {!readOnly && <Button type="text" danger icon={<DeleteOutlined />} aria-label={`删除题目 ${index + 1}`}
              onClick={() => setEditor({ ...editor, questions: editor.questions.filter(item => item.id !== question.id) })} />}
          </div>)}
          {!readOnly && <Button className="self-start" disabled={editor.questions.length >= 20}
            onClick={() => setEditor({ ...editor, questions: [...editor.questions, { id: uuidv4(), title: '', required: false }] })}>添加题目</Button>}
        </div>
      </div>}
    </ItsmDrawer>
  </div>;
}
