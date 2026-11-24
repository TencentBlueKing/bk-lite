import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, DatePicker, Form, Input, Modal, Radio, Select, Table } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { v4 as uuid } from 'uuid';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import type { AnalysisScope, HistoryAnalysisApi, Objective, Preview } from '@/app/opspilot/api/historyAnalysis';

dayjs.extend(utc);
dayjs.extend(timezone);

interface Props {
  api: HistoryAnalysisApi;
  skillId: string;
  channel?: number;
  channelName?: string;
  person: string;
  onClose: () => void;
  onCreated: () => void;
}

interface SessionOption {
  session_id: string;
  title: string;
  person_display: string;
  channel_name: string;
  channel_type: string;
}

function SessionPicker({ skillId, selected, onChange, channel, person }: {
  skillId: string; selected: string[]; onChange: (ids: string[]) => void; channel?: number; person: string;
}) {
  const { t } = useTranslation();
  const { fetchAdminSkillConversations } = useSkillApi();
  const fetchRef = useRef(fetchAdminSkillConversations);
  fetchRef.current = fetchAdminSkillConversations;
  const [rows, setRows] = useState<SessionOption[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    fetchRef.current({ skill_id: skillId, title, page, page_size: 5, channel_id: channel, person })
      .then(data => { if (active) { setRows(data.items); setCount(data.count); } })
      .catch(() => { if (active) { setRows([]); setFailed(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [skillId, title, page, channel, person]);
  return <div className="space-y-2">
    <Input.Search allowClear placeholder={t('skill.analysis.search')} onSearch={v => { setTitle(v); setPage(1); }} />
    {failed && <Alert type="error" message={t('skill.analysis.loadError')} />}
    <Table<SessionOption> size="small" rowKey="session_id" dataSource={rows} loading={loading}
      rowSelection={{ preserveSelectedRowKeys: true, selectedRowKeys: selected, onChange: keys => onChange(keys.map(String)),
        getCheckboxProps: row => ({ disabled: selected.length >= 50 && !selected.includes(row.session_id) }) }}
      columns={[
        { title: t('skill.history.title'), dataIndex: 'title', ellipsis: true },
        { title: t('skill.history.user'), dataIndex: 'person_display', ellipsis: true },
        { title: t('skill.history.channel'), dataIndex: 'channel_name', ellipsis: true,
          render: (name: string, row) => name || t(`skill.channel.types.${row.channel_type}`, row.channel_type) },
      ]}
      pagination={{ size: 'small', current: page, pageSize: 5, total: count, onChange: setPage, showSizeChanger: false }} />
    <span>{t('skill.analysis.selected', undefined, { count: selected.length })}</span>
  </div>;
}

export default function AnalysisConfig({ api, skillId, channel, channelName, person, onClose, onCreated }: Props) {
  const { t } = useTranslation();
  const { timeZone } = useLocalizedTime();
  const [mode, setMode] = useState<AnalysisScope['scope']>('range');
  const [dates, setDates] = useState<[Dayjs, Dayjs] | null>(() => [dayjs().tz(timeZone).subtract(6, 'day'), dayjs().tz(timeZone)]);
  const [selected, setSelected] = useState<string[]>([]);
  const [objective, setObjective] = useState<Objective>('overview');
  const [name, setName] = useState<string | null>(null);
  const [focus, setFocus] = useState('');
  const [requestId] = useState(() => uuid());
  const [submitting, setSubmitting] = useState(false);
  const submitLock = useRef(false);
  const [failed, setFailed] = useState(false);
  const [preview, setPreview] = useState<{ key: AnalysisScope; data?: Preview }>();
  const scope = useMemo<AnalysisScope | null>(() => {
    if (mode === 'sessions') return selected.length ? { scope: 'sessions', session_ids: selected } : null;
    return dates && { scope: 'range', start: dayjs.tz(dates[0].format('YYYY-MM-DD'), timeZone).toISOString(), end: dayjs.tz(dates[1].add(1, 'day').format('YYYY-MM-DD'), timeZone).toISOString(),
      channel_id: channel, person: person || undefined };
  }, [mode, dates, channel, person, selected, timeZone]);

  useEffect(() => {
    if (!scope) return;
    let active = true;
    const timer = setTimeout(() => {
      api.preview(scope).then(data => { if (active) setPreview({ key: scope, data }); })
        .catch(() => { if (active) setPreview({ key: scope }); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [api, scope]);

  const result = preview?.key === scope ? preview : undefined;
  const taskName = name ?? `${t(`skill.analysis.${objective}`)} · ${dayjs().format('YYYY-MM-DD')}`;
  const ready = !!(scope && taskName.trim() && result?.data && !result.data.issue);
  async function submit() {
    if (!ready || !scope || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setFailed(false);
    try {
      await api.create(scope, { objective, focus, name: taskName.trim(), request_id: requestId });
      onCreated();
    } catch { setFailed(true); }
    finally { submitLock.current = false; setSubmitting(false); }
  }

  return <Modal open width={660} title={t('skill.analysis.new')} okText={t('skill.analysis.create')} cancelText={t('common.cancel')}
    onCancel={() => { if (!submitLock.current) onClose(); }} onOk={submit}
    confirmLoading={submitting} okButtonProps={{ disabled: !ready }} maskClosable={false}>
    <Form layout="vertical" disabled={submitting}>
      <Form.Item label={t('skill.analysis.scope')}>
        <Radio.Group value={mode} onChange={event => setMode(event.target.value)}
          options={['range', 'sessions'].map(value => ({ value, label: t(`skill.analysis.${value}`) }))} />
      </Form.Item>
      {mode === 'range' && <p className="mb-2 text-[var(--color-text-3)]">{t('skill.analysis.rangeHint')}</p>}
      {(channelName || person) && <p className="mb-2 text-[var(--color-text-3)]">
        {[channelName, person].filter(Boolean).join(' · ')}</p>}
      {mode === 'range'
        ? <DatePicker.RangePicker className="w-full" value={dates} disabledDate={d => d.format('YYYY-MM-DD') > dayjs().tz(timeZone).format('YYYY-MM-DD')}
            onChange={value => setDates(value?.[0] && value[1] ? [value[0], value[1]] : null)} />
        : <SessionPicker skillId={skillId} channel={channel} person={person} selected={selected} onChange={setSelected} />}
      <div aria-live="polite" className="my-3">
        {scope && <Alert showIcon type={result && (!result.data || result.data.issue) ? 'warning' : 'info'}
          message={!result ? t('skill.analysis.previewing') : !result.data ? t('skill.analysis.loadError') :
          result.data.issue ? t(`skill.analysis.${result.data.issue}`) : t('skill.analysis.coverage', undefined, {
            sessions: result.data.conversation_count, questions: result.data.question_count,
          })} />}
      </div>
      <Form.Item label={t('skill.analysis.objective')}>
        <Select<Objective> value={objective} onChange={setObjective} options={(['overview', 'needs', 'quality'] as const)
          .map(value => ({ value, label: t(`skill.analysis.${value}`) }))} />
        <details className="mt-2 text-[var(--color-text-3)]">
          <summary className="cursor-pointer">{t('skill.analysis.prompt')}</summary>
          <p className="mt-1">{t(`skill.analysis.${objective}Prompt`)}</p>
        </details>
      </Form.Item>
      <Form.Item htmlFor="analysis-focus" label={t('skill.analysis.focus')}><Input.TextArea id="analysis-focus" value={focus} maxLength={500} rows={2}
        onChange={e => setFocus(e.target.value)} /></Form.Item>
      <Form.Item required htmlFor="analysis-name" label={t('skill.analysis.name')}><Input id="analysis-name" value={taskName} maxLength={120} onChange={e => setName(e.target.value)} /></Form.Item>
      {failed && <Alert type="error" message={t('skill.analysis.createError')} />}
    </Form>
  </Modal>;
}
