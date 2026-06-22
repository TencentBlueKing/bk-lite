'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Descriptions, Empty, Input, Spin, Tag } from 'antd';
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '../../../../utils/i18n';
import { useCopy } from '../../../../hooks/useCopy';
import { K8sMeta, K8sRenderParams, SourceItem } from '../../types/integration';

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
    return <Empty description={t('common.noData')} />;
  }

  const deployFile = meta.download_files.find((file) => file.key === 'deploy_yaml');

  const fieldLabelClassName = 'mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]';
  const codeBlockClassName = 'relative overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-5 py-4';
  const copyIconClassName = 'absolute top-1/2 right-3 -translate-y-1/2 cursor-pointer text-[var(--color-text-3)] hover:text-[var(--color-primary)]';

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
          <div className={codeBlockClassName}>
            <pre className="overflow-x-auto pr-10 text-[13px] leading-6 text-[var(--color-text-1)] whitespace-pre-wrap break-all">
              <code>{`docker pull ${meta.image_reference}`}</code>
            </pre>
            <CopyOutlined
              className={copyIconClassName}
              onClick={() => copy(`docker pull ${meta.image_reference}`)}
            />
          </div>
          <div className={codeBlockClassName}>
            <pre className="overflow-x-auto pr-10 text-[13px] leading-6 text-[var(--color-text-1)] whitespace-pre-wrap break-all">
              <code>docker load -i kubernetes-event-exporter.tar</code>
            </pre>
            <CopyOutlined
              className={copyIconClassName}
              onClick={() => copy('docker load -i kubernetes-event-exporter.tar')}
            />
          </div>
        </div>
      ),
    },
    {
      key: 'config',
      title: t('integration.renderedConfig'),
      eyebrow: t('integration.guideStep', '', { num: '04' }),
      description: t('integration.renderedConfigDesc'),
      content: (
        <div className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]">
          <Descriptions bordered size="small" column={1} labelStyle={{ width: 220, fontSize: 12, color: 'var(--color-text-3)' }}>
          <Descriptions.Item label="CLUSTER_NAME">
            {t('integration.clusterNameHelp')}
          </Descriptions.Item>
          <Descriptions.Item label="BK_LITE_RECEIVER_URL">
            <div className="flex items-center gap-2 break-all">
              <span>{meta.receiver_url}</span>
              <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(meta.receiver_url)} />
            </div>
          </Descriptions.Item>
          <Descriptions.Item label="BK_LITE_SECRET">
            {selectedTeamSecret ? (
              <div className="flex items-center gap-2">
                <span>******************</span>
                <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(selectedTeamSecret)} />
              </div>
            ) : (
              <span className="text-[var(--color-text-3)]">{'<' + t('integration.selectTeamPlaceholder') + '>'}</span>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="BK_LITE_SOURCE_ID">
            <Tag color="blue">{meta.source_id}</Tag>
            <span className="ml-2 text-[var(--color-text-3)]">{t('integration.sourceIdFixed')}</span>
          </Descriptions.Item>
          <Descriptions.Item label="BK_LITE_PUSH_SOURCE_ID">
            <div className="flex items-center gap-2">
              <Tag color="gold">{meta.push_source_id_default}</Tag>
              {meta.push_source_id_configurable && (
                <span className="text-[var(--color-text-3)]">{t('integration.pushSourceConfigurable')}</span>
              )}
            </div>
          </Descriptions.Item>
          </Descriptions>
        </div>
      ),
    },
    {
      key: 'apply',
      title: t('integration.applyToCluster'),
      eyebrow: t('integration.guideStep', '', { num: '05' }),
      description: t('integration.applyToClusterDesc'),
      content: (
        <div className={codeBlockClassName}>
          <pre className="overflow-x-auto pr-10 text-[13px] leading-6 text-[var(--color-text-1)] whitespace-pre-wrap break-all">
            <code>kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml</code>
          </pre>
          <CopyOutlined
            className={copyIconClassName}
            onClick={() => copy('kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml')}
          />
        </div>
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
        <div className="mb-4 rounded-[18px] border border-[var(--color-primary-bg-active)] bg-[var(--color-bg-1)] p-4">
          <h4 className="mb-3 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
            {t('integration.credentialsAndExamples')}
          </h4>
          {credentialsSlot}
        </div>
      ) : null}
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={step.key} className="relative pl-12 md:pl-14">
            <div className="absolute left-0 top-0 flex h-full w-12 justify-center md:w-14">
              {index < steps.length - 1 ? (
                <div className="absolute left-[19px] top-10 bottom-0 w-px bg-[linear-gradient(to_bottom,var(--color-border-3),color-mix(in_srgb,var(--color-border-1)_55%,transparent))] md:left-[23px]" />
              ) : null}
              <div className="relative z-10 flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-border-2)] bg-[var(--color-fill-1)] text-[12px] font-semibold text-[var(--color-primary)]">
                {index + 1}
              </div>
            </div>

            <div className="rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-5 py-5 sm:px-6">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {step.eyebrow}
                </div>
                <div className="h-px min-w-[72px] flex-1 bg-[var(--color-border-1)]" />
              </div>
              <div className="mt-3 text-[18px] font-semibold leading-7 text-[var(--color-text-1)]">
                {step.title}
              </div>
              <div className="mt-1.5 max-w-[760px] text-[13px] leading-6 text-[var(--color-text-2)]">
                {step.description}
              </div>
              <div className="mt-5">{step.content}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-5">
        <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-primary)]">
          Notes
        </div>
        <h4 className="mt-1 text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
          {t('integration.k8sGuideNotes')}
        </h4>
        <div className="mt-3 space-y-2">
          {meta.notes.map((note: string, index: number) => (
            <div key={`${note}-${index}`} className="flex items-start gap-2 text-[13px] leading-6 text-[var(--color-text-2)]">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
              <span>{note}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default K8sGuide;
