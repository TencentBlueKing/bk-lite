import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Drawer, Empty, List, Pagination, Space, Spin, Tag } from 'antd';
import { ArrowLeftOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { saveAs } from 'file-saver';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useHistoryAnalysisApi, type AnalysisReport, type AnalysisTask, type Evidence } from '@/app/opspilot/api/historyAnalysis';
import AnalysisConfig from './AnalysisConfig';

interface Props {
  skillId: string;
  channel?: number;
  channelName?: string;
  person: string;
  onClose: () => void;
  onEvidence: (evidence: Evidence) => void;
}

const colors = { queued: 'default', running: 'processing', completed: 'success', failed: 'error' };

export default function AnalysisDrawer({ skillId, channel, channelName, person, onClose, onEvidence }: Props) {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const api = useHistoryAnalysisApi(skillId);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [items, setItems] = useState<AnalysisTask[]>([]);
  const [total, setTotal] = useState(0);
  const [editing, setEditing] = useState(false);
  const [report, setReport] = useState<AnalysisReport>();
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [actionError, setActionError] = useState(false);
  const [busy, setBusy] = useState(false);
  const actionLock = useRef(false);
  useEffect(() => {
    if (report) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const refresh = async () => {
      try {
        const data = await api.list(page);
        if (!active) return;
        setListError(false);
        setItems(data.items);
        setTotal(data.count);
        if (data.items.some(item => item.status === 'queued' || item.status === 'running')) {
          timer = setTimeout(refresh, 3000);
        }
      } catch { if (active) setListError(true); }
      finally { if (active) setLoading(false); }
    };
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [api, page, revision, report]);

  async function perform(action: () => Promise<void>) {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setActionError(false);
    try { await action(); }
    catch { setActionError(true); }
    finally { actionLock.current = false; setBusy(false); }
  }

  function scopeLabel(task: AnalysisTask) {
    const s = task.scope;
    const channels = s.channel_types?.map(type => t(`skill.channel.types.${type}`, type)).join(' / ');
    if (s.scope === 'sessions') return [t('skill.analysis.sessions'), channels].filter(Boolean).join(' · ');
    const dates = `${convertToLocalizedTime(s.start, 'YYYY-MM-DD')} — ${convertToLocalizedTime(new Date(Date.parse(s.end) - 1).toISOString(), 'YYYY-MM-DD')}`;
    const binding = s.channel_id && `${t('skill.history.channel')} #${s.channel_id}`;
    return [dates, channels, binding, s.person].filter(Boolean).join(' · ');
  }

  const reload = () => setRevision(v => v + 1);
  return <Drawer open width="min(820px, 100vw)" onClose={onClose}
    title={report ? <Space><Button type="text" icon={<ArrowLeftOutlined />} aria-label={t('skill.analysis.back')}
      onClick={() => { setReport(undefined); setActionError(false); }} />{report.name}</Space> : t('skill.analysis.title')}
    extra={report
      ? <Button icon={<DownloadOutlined />} loading={busy} onClick={() => perform(async () => {
        const pdf = await api.pdf(report.id);
        saveAs(pdf, `${report.name}.pdf`);
      })}>{t('skill.analysis.pdf')}</Button>
      : <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing(true)}>{t('skill.analysis.new')}</Button>}>
    {actionError && <Alert type="error" showIcon message={t('skill.analysis.actionError')} />}
    {report ? <article className="space-y-5">
      <section className="rounded-lg bg-[var(--color-fill-1)] p-4">
        <h3 className="font-semibold">{t('skill.analysis.scope')}</h3>
        <p>{scopeLabel(report)}</p>
        <p>{t('skill.analysis.coverage', undefined, { sessions: report.conversation_count, questions: report.question_count })}</p>
        <p className="text-[var(--color-text-3)]">{t(`skill.analysis.${report.objective}`)} · {report.creator} · {convertToLocalizedTime(report.created_at)}</p>
        {report.focus && <p>{report.focus}</p>}
      </section>
      {report.findings.map((item, index) => <section key={index} className="space-y-2 border-b border-[var(--color-border-1)] pb-4">
        <h3 className="whitespace-pre-wrap font-semibold">{item.finding}</h3>
        <p className="whitespace-pre-wrap">{t('skill.analysis.suggestion')} · {item.suggestion}</p>
        <Space wrap>{item.evidence.map(ref => <Button size="small" key={ref.message_id} onClick={() => onEvidence(ref)}>
          {t('skill.analysis.evidence')} #{ref.message_id}
        </Button>)}</Space>
      </section>)}
    </article> : listError ? <Alert type="error" message={t('skill.analysis.loadError')}
      action={<Button icon={<ReloadOutlined />} onClick={reload}>{t('common.refresh')}</Button>} />
    : <Spin spinning={loading || busy}>
      <List dataSource={items} locale={{ emptyText: <Empty description={t('skill.analysis.noTasks')} /> }}
        renderItem={item => <List.Item actions={[
          item.status === 'completed' ? <Button key="view" type="link" disabled={busy} onClick={() => perform(async () => setReport(await api.report(item.id)))}>
            {t('skill.analysis.view')}</Button> : item.status === 'failed'
            ? <Button key="retry" type="link" disabled={busy} onClick={() => perform(async () => { await api.retry(item.id); reload(); })}>
              {t('skill.analysis.retry')}</Button> : null,
        ]}>
          <List.Item.Meta title={<Space wrap>{item.name}<Tag color={colors[item.status]}>{t(`skill.analysis.${item.status}`)}</Tag></Space>}
            description={<div>
              <div>{scopeLabel(item)} · {t('skill.analysis.coverage', undefined, { sessions: item.conversation_count, questions: item.question_count })}</div>
              <div>{item.creator} · {convertToLocalizedTime(item.created_at)}</div>
              {item.failure && <div>{t(`skill.analysis.${item.failure}`)}</div>}
            </div>} />
        </List.Item>} />
      {total > 10 && <Pagination current={page} total={total} pageSize={10} onChange={setPage} showSizeChanger={false} />}
    </Spin>}
    {editing && <AnalysisConfig api={api} skillId={skillId} channel={channel} channelName={channelName} person={person}
      onClose={() => setEditing(false)} onCreated={() => { setEditing(false); setPage(1); reload(); }} />}
  </Drawer>;
}
