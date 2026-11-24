'use client';

import { Input } from 'antd';
import dayjs from 'dayjs';
import { FieldRow } from '../../components/field-row';
import { WorkScheduleBoard } from '../../components/work-schedule-board';

interface ChangeWindow {
  id: number;
  name: string;
  start_at: string | null;
  end_at: string | null;
}

function localTime(value: string | null | undefined, format: string) {
  return value && dayjs(value).isValid() ? dayjs(value).format(format) : '';
}

const timestamp = (value: string | null) => localTime(value, 'YYYY-MM-DD HH:mm:ss') || '—';

export default function Page() {
  return <WorkScheduleBoard kind="changes" title="变更窗口" columns={[
    { title: '开始时间', dataIndex: 'start_at', key: 'start_at', render: timestamp },
    { title: '结束时间', dataIndex: 'end_at', key: 'end_at', render: timestamp },
  ]}
    toDraft={(row?: ChangeWindow) => ({
      name: row?.name ?? '', startAt: localTime(row?.start_at, 'YYYY-MM-DDTHH:mm:ss'), endAt: localTime(row?.end_at, 'YYYY-MM-DDTHH:mm:ss'),
    })}
    toPayload={draft => {
      const start = dayjs(draft.startAt);
      const end = dayjs(draft.endAt);
      if (!start.isValid() || !end.isValid()) throw new Error('请选择开始和结束时间');
      if (!end.isAfter(start)) throw new Error('结束时间须晚于开始时间');
      return { name: draft.name, start_at: start.toISOString(), end_at: end.toISOString() };
    }}
    searchValues={row => [timestamp(row.start_at), timestamp(row.end_at)]}
    renderFields={(draft, setDraft) => <>
      <FieldRow label="开始时间"><Input type="datetime-local" step={1} required aria-label="开始时间" value={draft.startAt}
        onChange={event => setDraft({ ...draft, startAt: event.target.value })} /></FieldRow>
      <FieldRow label="结束时间"><Input type="datetime-local" step={1} required aria-label="结束时间" value={draft.endAt}
        onChange={event => setDraft({ ...draft, endAt: event.target.value })} /></FieldRow>
    </>} />;
}
