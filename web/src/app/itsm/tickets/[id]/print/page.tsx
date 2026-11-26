'use client';

import { PrinterOutlined } from '@ant-design/icons';
import { Alert, Button } from 'antd';
import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { ItsmBackButton } from '../../../components/back-button';
import { useTranslation } from '@/utils/i18n';
import { PrintDocument, PrintDocumentSkeleton } from '../../../components/print-document';

type TicketPrintState =
  | { status: 'loading' }
  | { status: 'ready'; html: string }
  | { status: 'error'; message: string };

export default function Page() {
  const id = Number(useParams<{ id: string }>().id);
  const fromTicketCenter = useSearchParams().get('from') === 'tickets';
  const { getTicketPrint, ready } = useItsmApi();
  const frame = useRef<HTMLIFrameElement>(null);
  const { t } = useTranslation();
  const [preview, setPreview] = useState<TicketPrintState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const fallback = t('itsm.print.ticketFailed');
  const [canPrint, setCanPrint] = useState(false);

  useEffect(() => {
    if (!ready) return;
    let current = true;
    setPreview({ status: 'loading' });
    setCanPrint(false);
    void getTicketPrint(id).then(({ html }) => {
      if (current) setPreview({ status: 'ready', html });
    }).catch(error => {
      if (current) setPreview({ status: 'error', message: error instanceof Error ? error.message : fallback });
    });
    return () => { current = false; };
  }, [attempt, fallback, getTicketPrint, id, ready]);

  return <section className="mx-auto flex w-full flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <header className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] pb-3">
      <ItsmBackButton label={t('itsm.print.backToDetail')} href={`/itsm/tickets/${id}${fromTicketCenter ? '?from=tickets' : ''}`} />
      <h1 className="text-base font-semibold">{t('itsm.print.title')}</h1>
      <Button type="primary" icon={<PrinterOutlined aria-hidden />} className="ml-auto" disabled={preview.status !== 'ready' || !canPrint}
        onClick={() => frame.current?.contentWindow?.print()}>{t('itsm.print.action')}</Button>
    </header>
    {preview.status === 'error' && <Alert type="error" message={preview.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>{t('itsm.common.retry')}</Button>} />}
    {preview.status === 'loading' && <PrintDocumentSkeleton label={t('itsm.print.loading')} />}
    {preview.status === 'ready' && <PrintDocument title={t('itsm.print.ticketPreview')} html={preview.html} frameRef={frame} onLoad={() => setCanPrint(true)} />}
  </section>;
}
