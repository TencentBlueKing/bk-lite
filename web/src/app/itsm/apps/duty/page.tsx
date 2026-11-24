'use client';

import { Input, Segmented } from 'antd';
import dayjs from 'dayjs';
import { useContext, useState } from 'react';
import { UserInfoContext } from '@/context/userInfo';
import { FieldRow } from '../../components/field-row';
import { ItsmListTabs } from '../../components/list-controls';
import { UserSelector } from '../../components/user-selector';
import { WorkScheduleBoard } from '../../components/work-schedule-board';
import { DutyCalendar, memberNames, type DutyShift } from './duty-calendar';

export default function Page() {
  const user = useContext(UserInfoContext);
  const username = user?.loading ? '' : user?.username;
  const [scope, setScope] = useState('all');
  const [view, setView] = useState<'list' | 'calendar'>('list');
  const [date, setDate] = useState(() => dayjs());

  return <WorkScheduleBoard kind="duties" title="值班排班" columns={[
    { title: '值班日期', dataIndex: 'day', key: 'day', render: (day: string | null) => day || '—' },
    { title: '值班人员', dataIndex: 'members', key: 'members', ellipsis: true,
      render: (members: unknown) => memberNames(members).join('、') || '—' },
  ]} view={{
    key: scope,
    leading: <ItsmListTabs activeKey={scope} onChange={setScope} items={[
      { key: 'all', label: '全部排班' },
      { key: 'mine', label: '我的值班', disabled: !username },
    ]} />,
    filters: <Segmented<'list' | 'calendar'> aria-label="排班视图" value={view} onChange={setView}
      options={[{ label: '列表', value: 'list' }, { label: '月历', value: 'calendar' }]} />,
    includes: scope === 'mine' ? (shift: DutyShift) => Boolean(username && memberNames(shift.members).includes(username)) : undefined,
    newDraft: {
      ...(view === 'calendar' ? { day: date.format('YYYY-MM-DD') } : {}),
      ...(scope === 'mine' && username ? { members: [username] } : {}),
    },
    render: view === 'calendar' ? options => <DutyCalendar {...options} date={date} onChange={setDate} /> : undefined,
  }}
    toDraft={(row?: DutyShift) => ({ name: row?.name ?? '', day: row?.day ?? '', members: memberNames(row?.members) })}
    toPayload={draft => {
      if (!draft.day) throw new Error('请选择值班日期');
      if (!draft.members.length) throw new Error('请至少选择一名值班人员');
      return draft;
    }}
    searchValues={row => [row.day ?? '', ...memberNames(row.members)]}
    renderFields={(draft, setDraft) => <>
      <FieldRow label="值班日期"><Input type="date" required aria-label="值班日期" value={draft.day}
        onChange={event => setDraft({ ...draft, day: event.target.value })} /></FieldRow>
      <FieldRow label="值班人员"><UserSelector ariaLabel="值班人员" value={draft.members}
        onChange={members => setDraft({ ...draft, members })} /></FieldRow>
    </>} />;
}
