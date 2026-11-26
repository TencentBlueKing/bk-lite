'use client';

import { Select } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

export interface ArticleTicket {
  id: number;
  sn: string;
  title: string;
}

interface ArticleTicketPickerProps {
  tickets: ArticleTicket[];
  disabled: boolean;
  onChange: (tickets: ArticleTicket[]) => void;
}

export function ArticleTicketPicker({ tickets, disabled, onChange }: ArticleTicketPickerProps) {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [matches, setMatches] = useState<ArticleTicket[]>([]);
  const [searching, setSearching] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || disabled) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      setFailed(false);
      void get<{ items: ArticleTicket[] }>('/itsm/api/tickets', {
        params: { q: keyword.trim(), fields: 'sn,title', page_size: 20 },
        signal: controller.signal, suppressErrorNotification: true,
      }).then(result => {
        if (!controller.signal.aborted) setMatches(result.items);
      }).catch(() => {
        if (!controller.signal.aborted) {
          setMatches([]);
          setFailed(true);
        }
      }).finally(() => {
        if (!controller.signal.aborted) setSearching(false);
      });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [open, disabled, get, keyword]);

  const byId = new Map([...tickets, ...matches].map(ticket => [ticket.id, ticket]));
  return <div className="flex flex-col gap-2">
    <span>{t('itsm.knowledge.relatedTickets')}</span>
    <Select aria-label={t('itsm.knowledge.relatedTickets')} mode="multiple" disabled={disabled} showSearch filterOption={false} virtual={false}
      placeholder={t('itsm.knowledge.ticketSearch')} onOpenChange={setOpen} onSearch={setKeyword} loading={searching}
      value={tickets.map(ticket => ticket.id)}
      options={[...byId.values()].map(ticket => ({ value: ticket.id, label: `${ticket.title}（${ticket.sn}）`, ticket }))}
      onChange={ids => onChange(ids.flatMap(id => byId.get(id) ?? []))}
      optionRender={({ data }) => <div className="flex flex-col gap-1 py-1">
        <span className="whitespace-normal break-words">{data.ticket.title}</span>
        <span className="text-xs text-[var(--color-text-3)]">{data.ticket.sn}</span>
      </div>}
      notFoundContent={searching ? t('itsm.knowledge.ticketSearching') : failed ? t('itsm.knowledge.ticketSearchFailed') : t('itsm.knowledge.noTickets')} />
  </div>;
}
