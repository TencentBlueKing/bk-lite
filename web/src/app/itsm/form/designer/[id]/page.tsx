'use client';

import { usePageLeave } from '@/app/itsm/components/page-leave';
import { Button, Drawer, Empty, Tag, message } from 'antd';
import { ItsmBackButton } from '@/app/itsm/components/back-button';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../../api/useItsmApi';
import { useTranslation } from '@/utils/i18n';
import { FormDesigner } from '../../../components/form-designer';
import { FormRenderer } from '../../../components/form-renderer';
import type { FormFieldSchema, FormSchema } from '../../../types';

interface FormDetail {
  name: string;
  schema: FormSchema;
  versions: Array<{ id: number; version_no: number; is_published: boolean }>;
}

export default function FormDesignerPage() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const formId = Number(params.id);
  const api = useItsmApi();
  const [detail, setDetail] = useState<FormDetail | null>(null);
  const [fields, setFields] = useState<FormFieldSchema[]>([]);
  const [preview, setPreview] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  usePageLeave(!!detail && JSON.stringify(fields)!==JSON.stringify(detail.schema?.fields || []));

  const load = useCallback(async () => {
    const data = await api.getForm(formId) as FormDetail;
    setDetail(data);
    setFields(data.schema?.fields || []);
  }, [api.getForm, formId]);

  useEffect(() => {
    if (!api.ready || !formId) {
      return;
    }
    void load().catch((error: unknown) => message.error(error instanceof Error ? error.message : t('itsm.ticket.loadFailed')));
  }, [api.ready, formId, load]);

  const schema: FormSchema = { version: 1, fields };

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.saveForm(formId, schema) as { version_no: number };
      message.success(t('itsm.design.draftSaved', undefined, { version: String(saved.version_no) }));
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.design.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    setBusy(true);
    try {
      const published = await api.publishForm(formId, schema) as { version_no: number };
      message.success(t('itsm.design.versionPublished', undefined, { version: String(published.version_no) }));
      await load();
      setHistoryOpen(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('itsm.design.publishFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3">
        <div className="flex items-center gap-3">
          <ItsmBackButton href="/itsm/form" label="返回表单列表" />
          <div className="h-4 w-px bg-[var(--color-border)]" />
          <span className="text-sm font-medium text-[var(--color-text-1)]">{detail?.name || t('itsm.design.formDesigner')}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setPreview((current) => !current)}>{preview ? t('itsm.design.backEdit') : t('itsm.design.previewForm')}</Button>
          <Button onClick={() => setHistoryOpen(true)}>{t('itsm.design.history')}</Button>
          <div className="mx-1 h-4 w-px bg-[var(--color-border)]" />
          <Button loading={busy} onClick={() => { void save(); }}>{t('itsm.design.saveDraft')}</Button>
          <Button type="primary" loading={busy} onClick={() => { void publish(); }}>{t('itsm.design.publishVersion')}</Button>
        </div>
      </div>
      {preview ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-6">
          <FormRenderer schema={schema} onSubmit={() => message.success(t('itsm.design.previewSubmitted'))} />
        </div>
      ) : (
        <FormDesigner fields={fields} onChange={setFields} />
      )}
      <Drawer title={t('itsm.design.history')} open={historyOpen} onClose={() => setHistoryOpen(false)}>
        {(detail?.versions || []).length ? (
          <div className="flex flex-col gap-2">
            {(detail?.versions || []).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2"
              >
                <span className="text-sm text-[var(--color-text-1)]">{t('itsm.design.versionLabel', undefined, { version: String(item.version_no) })}</span>
                <Tag color={item.is_published ? 'processing' : 'default'}>
                  {item.is_published ? t('itsm.design.publishedTag') : t('itsm.design.draft')}
                </Tag>
              </div>
            ))}
          </div>
        ) : (
          <Empty description={t('itsm.design.emptyHistory')} />
        )}
      </Drawer>
    </div>
  );
}
