'use client';

import { Alert, Button } from 'antd';
import { useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { PrintDocument, PrintDocumentSkeleton } from '../../components/print-document';

type PrintPreviewState =
  | { status: 'loading' }
  | { status: 'ready'; html: string }
  | { status: 'error'; message: string };

export default function PrintPreviewPage() {
  const { ready, previewPrintTemplate } = useItsmApi();
  const { t } = useTranslation();
  const [preview, setPreview] = useState<PrintPreviewState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const fallback = t('itsm.print.sampleFailed');

  useEffect(() => {
    if (!ready) return;
    let current = true;
    setPreview({ status: 'loading' });
    void previewPrintTemplate().then(({ html }) => {
      if (current) setPreview({ status: 'ready', html });
    }).catch(error => {
      if (current) setPreview({ status: 'error', message: error instanceof Error ? error.message : fallback });
    });
    return () => { current = false; };
  }, [attempt, fallback, previewPrintTemplate, ready]);

  return <section className="mx-auto flex w-full flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <header className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] pb-3">
      <h1 className="text-base font-semibold">{t('itsm.print.preview')}</h1>
      <p className="text-sm text-[var(--color-text-2)]">{t('itsm.print.sampleDescription')}</p>
    </header>
    {preview.status === 'loading' && <PrintDocumentSkeleton label={t('itsm.print.loading')} />}
    {preview.status === 'error' && <Alert type="error" message={preview.message}
      action={<Button onClick={() => setAttempt(value => value + 1)}>{t('itsm.common.retry')}</Button>} />}
    {preview.status === 'ready' && <PrintDocument title={t('itsm.print.samplePreview')} html={preview.html} />}
  </section>;
}
