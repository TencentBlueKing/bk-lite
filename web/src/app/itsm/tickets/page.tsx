'use client';

import { TicketWorkbench } from '../components/ticket-workbench';
import ListPageHeader from '@/components/list-page-header';
import { useTranslation } from '@/utils/i18n';

export default function TicketsPage() {
  const { t } = useTranslation();
  return <div className="flex flex-col"><ListPageHeader title={t('itsm.ticket.center')} /><TicketWorkbench /></div>;
}
