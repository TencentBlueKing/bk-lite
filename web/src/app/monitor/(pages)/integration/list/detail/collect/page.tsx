'use client';

import React, { useEffect, useState } from 'react';
import { Button, Empty, Modal, Spin, message } from 'antd';
import { useSearchParams } from 'next/navigation';
import CodeEditor from '@/components/code-editor';
import useIntegrationApi from '@/app/monitor/api/integration';
import { useTranslation } from '@/utils/i18n';

const CollectPage = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getSnmpCollectTemplate, updateSnmpCollectTemplate } =
    useIntegrationApi();
  const pluginId = searchParams.get('plugin_id') || '';
  const templateType = searchParams.get('template_type') || '';

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [content, setContent] = useState('');
  const [initialContent, setInitialContent] = useState('');

  useEffect(() => {
    if (!pluginId || templateType !== 'snmp') {
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      setLoadError('');
      try {
        const data = await getSnmpCollectTemplate(pluginId);
        setContent(data.content || '');
        setInitialContent(data.content || '');
      } catch (error: any) {
        const errorMessage = error?.message || t('common.operationFailed');
        setLoadError(errorMessage);
        message.error(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [pluginId, templateType]);

  const handleSave = () => {
    Modal.confirm({
      title: t('monitor.integrations.collectSaveTitle'),
      content: t('monitor.integrations.collectSaveConfirm'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        setSaving(true);
        try {
          const data = await updateSnmpCollectTemplate(pluginId, { content });
          setContent(data.content || '');
          setInitialContent(data.content || '');
          message.success(t('monitor.integrations.collectSaveSuccess'));
        } catch (error: any) {
          message.error(error?.message || t('common.operationFailed'));
        } finally {
          setSaving(false);
        }
      }
    });
  };

  if (templateType !== 'snmp') {
    return (
      <Empty description={t('monitor.integrations.collectNotSupported')} />
    );
  }

  return (
    <Spin spinning={loading}>
      <div className="px-[10px] h-[calc(100vh-270px)] overflow-y-auto">
        <div className="mb-4">
          <div className="mb-2 text-[20px] font-semibold text-[var(--color-text-1)]">
            {t('monitor.integrations.collect')}
          </div>
          <div className="text-[14px] text-[var(--color-text-2)]">
            {t('monitor.integrations.collectDescription')}
          </div>
          <div className="mt-2 text-[12px] text-[var(--color-text-3)]">
            {t('monitor.integrations.collectNote')}
          </div>
        </div>

        {!!loadError && (
          <div className="mb-4 rounded-md border border-[var(--color-warning)] bg-[var(--color-warning-bg)] px-4 py-3 text-[14px] text-[var(--color-warning-text)]">
            {t('monitor.integrations.collectLoadError')}
            {loadError}
          </div>
        )}

        <div className="mb-4 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-fill-1)]">
            <div className="text-sm font-medium text-[var(--color-text-1)]">
              {t('monitor.integrations.collectMetricSnippet')}
            </div>
            <div className="text-sm text-[var(--color-text-3)]">
              TOML / Telegraf SNMP Input
            </div>
          </div>
          <CodeEditor
            value={content}
            mode="toml"
            theme="monokai"
            width="100%"
            height="520px"
            onChange={(value: string) => setContent(value)}
            headerOptions={{ copy: true, fullscreen: true }}
            setOptions={{ showPrintMargin: false, useWorker: false }}
          />
        </div>

        <div className="my-4 flex justify-end">
          <Button
            type="primary"
            loading={saving}
            disabled={
              loading || !!loadError || content.trim() === initialContent.trim()
            }
            onClick={handleSave}
          >
            {t('common.save')}
          </Button>
        </div>
      </div>
    </Spin>
  );
};

export default CollectPage;
