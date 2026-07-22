'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Input, Spin } from 'antd';
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import AlarmIntegrationGuideCredentialsPanel from '@/app/alarm/components/integration-guide/CredentialsPanel';
import AlarmIntegrationGuideSectionPanel from '@/app/alarm/components/integration-guide/SectionPanel';
import CodeSnippet from '@/components/code-snippet';
import DetailListPanel from '@/components/detail-list-panel';
import GuideStepPanel from '@/components/guide-step-panel';
import NoteListPanel from '@/components/note-list-panel';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';
import type {
  K8sMeta,
  K8sRenderParams,
  SourceItem,
} from '@/app/alarm/types/integration-guide';

interface K8sGuideProps {
  source?: SourceItem;
  meta?: K8sMeta;
  loading?: boolean;
  onDownload: (fileKey: string, fileName: string, params: K8sRenderParams) => Promise<void>;
  credentialsSlot?: React.ReactNode;
  selectedTeamSecret?: string;
}

const K8sGuide: React.FC<K8sGuideProps> = ({
  source,
  meta,
  loading = false,
  onDownload,
  credentialsSlot,
  selectedTeamSecret,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const [serverUrl, setServerUrl] = useState('');
  const [clusterName, setClusterName] = useState('k8s_cluster');
  const [pushSourceId, setPushSourceId] = useState(meta?.push_source_id_default || 'k8s');
  const [insecureSkipVerify, setInsecureSkipVerify] = useState(true);

  useEffect(() => {
    if (!serverUrl && typeof window !== 'undefined') {
      setServerUrl(window.location.origin);
    }
  }, [serverUrl]);

  const renderParams = useMemo<K8sRenderParams>(() => ({
    server_url: serverUrl,
    cluster_name: clusterName,
    push_source_id: pushSourceId,
    team_secret: selectedTeamSecret,
    insecure_skip_verify: insecureSkipVerify,
  }), [serverUrl, clusterName, pushSourceId, selectedTeamSecret, insecureSkipVerify]);

  useEffect(() => {
    if (meta?.push_source_id_default) {
      setPushSourceId(meta.push_source_id_default);
    }
  }, [meta?.push_source_id_default]);

  if (loading) {
    return (
      <div className="p-4">
        <Spin spinning />
      </div>
    );
  }

  if (!source || !meta) {
    return <CompactEmptyState description={t('common.noData')} className="py-6" />;
  }

  const deployFile = meta.download_files.find((file) => file.key === 'deploy_yaml');

  const fieldLabelClassName = 'mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]';
  const steps = [
    {
      key: 'parameters',
      title: t('integration.fillDeployParams'),
      eyebrow: t('integration.guideStep', '', { num: '01' }),
      description: t('integration.fillDeployParamsDesc'),
      content: (
        <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <div className="lg:col-span-2">
            <div className={fieldLabelClassName}>
              {t('integration.serverUrlLabel')}
            </div>
            <Input
              value={serverUrl}
              onChange={(event) => setServerUrl(event.target.value)}
              placeholder="https://10.11.27.147:443"
            />
          </div>
          <div>
            <div className={fieldLabelClassName}>
              {t('integration.clusterNameLabel')}
            </div>
            <Input
              value={clusterName}
              onChange={(event) => setClusterName(event.target.value)}
              placeholder="orbstack-local"
            />
          </div>
          <div>
            <div className={fieldLabelClassName}>
              {t('integration.pushSourceIdLabel')}
            </div>
            <Input
              value={pushSourceId}
              onChange={(event) => setPushSourceId(event.target.value)}
              placeholder={meta.push_source_id_default}
            />
          </div>
          <div className="lg:col-span-2">
            <Checkbox
              checked={insecureSkipVerify}
              onChange={(event) => setInsecureSkipVerify(event.target.checked)}
            >
              {t('integration.k8sInsecureSkipVerifyLabel')}
            </Checkbox>
            <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-3)]">
              {t('integration.k8sInsecureSkipVerifyHelp')}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: 'yaml',
      title: t('integration.downloadDeployYaml'),
      eyebrow: t('integration.guideStep', '', { num: '02' }),
      description: t('integration.downloadDeployYamlDesc'),
      content: (
        <div className="space-y-4">
          <div>
            {deployFile ? (
              <Button
                icon={<DownloadOutlined />}
                onClick={() => onDownload(deployFile.key, deployFile.file_name, renderParams)}
                disabled={!serverUrl || !clusterName || !selectedTeamSecret}
              >
                {deployFile.display_name}
              </Button>
            ) : (
              <div className="text-sm text-[var(--color-text-3)]">{t('common.noData')}</div>
            )}
          </div>
          <div className="max-w-[680px] text-[13px] leading-6 text-[var(--color-text-2)]">
            {selectedTeamSecret
              ? '下载前请确认接入地址与集群名正确，避免后续重复改 YAML。'
              : '请先在顶部选择上报组织（或新建组织密钥）后再下载部署文件。'}
          </div>
        </div>
      ),
    },
    {
      key: 'image',
      title: t('integration.prepareImage'),
      eyebrow: t('integration.guideStep', '', { num: '03' }),
      description: t('integration.prepareImageDesc'),
      content: (
        <div className="space-y-4">
          <div className="rounded-[16px] bg-[var(--color-fill-1)] px-5 py-4">
            <div className={fieldLabelClassName}>{t('integration.imageReference')}</div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 break-all text-[13px] font-medium leading-6 text-[var(--color-text-1)]">
              <span className="min-w-0 flex-1 break-all">{meta.image_reference}</span>
              <Button className="self-center" type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(meta.image_reference)} />
            </div>
          </div>
          <CodeSnippet
            value={`docker pull ${meta.image_reference}`}
            copyable
          />
          <CodeSnippet
            value="docker load -i kubernetes-event-exporter.tar"
            copyable
          />
        </div>
      ),
    },
    {
      key: 'config',
      title: t('integration.renderedConfig'),
      eyebrow: t('integration.guideStep', '', { num: '04' }),
      description: t('integration.renderedConfigDesc'),
      content: (
        <DetailListPanel
          className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
          labelWidthClassName="w-40"
          items={[
            {
              label: 'CLUSTER_NAME',
              value: t('integration.clusterNameHelp'),
              copyable: false,
            },
            {
              label: 'BK_LITE_RECEIVER_URL',
              value: meta.receiver_url,
              copyValue: meta.receiver_url,
              copyable: true,
            },
            {
              label: 'BK_LITE_SECRET',
              value: selectedTeamSecret || '',
              displayValue: selectedTeamSecret
                ? '******************'
                : <span className="text-[var(--color-text-3)]">{`<${t('integration.selectTeamPlaceholder')}>`}</span>,
              copyValue: selectedTeamSecret || '',
              copyable: Boolean(selectedTeamSecret),
            },
            {
              label: 'BK_LITE_SOURCE_ID',
              value: meta.source_id,
              displayValue: (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[13px]">{meta.source_id}</span>
                  <span className="text-[var(--color-text-3)]">{t('integration.sourceIdFixed')}</span>
                </div>
              ),
              copyValue: meta.source_id,
              copyable: true,
            },
            {
              label: 'BK_LITE_PUSH_SOURCE_ID',
              value: meta.push_source_id_default,
              displayValue: (
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[13px]">{meta.push_source_id_default}</span>
                  {meta.push_source_id_configurable ? (
                    <span className="text-[var(--color-text-3)]">{t('integration.pushSourceConfigurable')}</span>
                  ) : null}
                </div>
              ),
              copyValue: meta.push_source_id_default,
              copyable: true,
            },
          ]}
        />
      ),
    },
    {
      key: 'apply',
      title: t('integration.applyToCluster'),
      eyebrow: t('integration.guideStep', '', { num: '05' }),
      description: t('integration.applyToClusterDesc'),
      content: (
        <CodeSnippet
          value="kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml"
          copyable
        />
      ),
    },
    {
      key: 'verify',
      title: t('integration.verifyResult'),
      eyebrow: t('integration.guideStep', '', { num: '06' }),
      description: t('integration.verifyResultDesc'),
      content: (
        <div className="rounded-[16px] border border-dashed border-[var(--color-border-3)] bg-[var(--color-fill-1)] px-5 py-4 text-[13px] leading-6 text-[var(--color-text-2)]">
          {t('integration.verifyResultHelp')}
        </div>
      ),
    },
  ];

  return (
    <div className="max-h-[calc(100vh-330px)] overflow-y-auto py-2">
      {credentialsSlot ? (
        <AlarmIntegrationGuideCredentialsPanel
          title={t('integration.credentialsAndExamples')}
          className="mb-4 rounded-[18px] border border-[var(--color-primary-bg-active)] bg-[var(--color-bg-1)]"
        >
          {credentialsSlot}
        </AlarmIntegrationGuideCredentialsPanel>
      ) : null}
      <div className="space-y-4">
        {steps.map((step, index) => (
          <GuideStepPanel
            key={step.key}
            step={index + 1}
            variant="timeline"
            showConnector={index < steps.length - 1}
            eyebrow={step.eyebrow}
            title={step.title}
            description={step.description}
          >
            {step.content}
          </GuideStepPanel>
        ))}
      </div>

      <AlarmIntegrationGuideSectionPanel
        className="mt-5 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
        headerClassName="px-5 pt-5"
        bodyClassName="px-5 pb-5"
        title={t('integration.k8sGuideNotes')}
        description="Notes"
        descriptionClassName="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-primary)]"
      >
        <NoteListPanel
          className="mt-3"
          items={meta.notes}
        />
      </AlarmIntegrationGuideSectionPanel>
    </div>
  );
};

export default K8sGuide;
