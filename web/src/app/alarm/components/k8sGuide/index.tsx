'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Descriptions, Empty, Input, Space, Spin, Tag } from 'antd';
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';
import { K8sMeta, K8sRenderParams, SourceItem } from '@/app/alarm/types/integration';

interface K8sGuideProps {
  source?: SourceItem;
  meta?: K8sMeta;
  loading?: boolean;
  onDownload: (fileKey: string, fileName: string, params: K8sRenderParams) => Promise<void>;
}

const K8sGuide: React.FC<K8sGuideProps> = ({
  source,
  meta,
  loading = false,
  onDownload,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const [serverUrl, setServerUrl] = useState('');
  const [clusterName, setClusterName] = useState('k8s_cluster');
  const [pushSourceId, setPushSourceId] = useState(meta?.push_source_id_default || 'k8s');

  useEffect(() => {
    if (!serverUrl && typeof window !== 'undefined') {
      setServerUrl(window.location.origin);
    }
  }, [serverUrl]);

  const renderParams = useMemo<K8sRenderParams>(() => ({
    server_url: serverUrl,
    cluster_name: clusterName,
    push_source_id: pushSourceId,
  }), [serverUrl, clusterName, pushSourceId]);

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

  return (
    <div className="p-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      <h4 className="mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.deploySteps')}
      </h4>
      <div className="rounded border border-[var(--color-border-1)] bg-[var(--color-bg-5)] p-4 space-y-4">
        <div>
          <div className="font-medium mb-2">1. {t('integration.fillDeployParams')}</div>
          <div className="rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3 space-y-3">
            <div>
              <div className="text-sm mb-1">{t('integration.serverUrlLabel')}</div>
              <Input
                value={serverUrl}
                onChange={(event) => setServerUrl(event.target.value)}
                placeholder="https://10.11.27.147:443"
              />
            </div>
            <div>
              <div className="text-sm mb-1">{t('integration.clusterNameLabel')}</div>
              <Input
                value={clusterName}
                onChange={(event) => setClusterName(event.target.value)}
                placeholder="orbstack-local"
              />
            </div>
            <div>
              <div className="text-sm mb-1">{t('integration.pushSourceIdLabel')}</div>
              <Input
                value={pushSourceId}
                onChange={(event) => setPushSourceId(event.target.value)}
                placeholder={meta.push_source_id_default}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="font-medium mb-2">2. {t('integration.downloadDeployYaml')}</div>
          <Space wrap>
            {meta.download_files.filter((file: K8sMeta['download_files'][number]) => file.key === 'deploy_yaml').map((file: K8sMeta['download_files'][number]) => (
              <Button
                key={file.key}
                icon={<DownloadOutlined />}
                onClick={() => onDownload(file.key, file.file_name, renderParams)}
                disabled={!serverUrl || !clusterName}
              >
                {file.display_name}
              </Button>
            ))}
          </Space>
        </div>

        <div>
          <div className="font-medium mb-2">3. {t('integration.prepareImage')}</div>
          <div className="rounded border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3 space-y-2">
            <div className="flex items-center gap-2 break-all">
              <span>{meta.image_reference}</span>
              <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copy(meta.image_reference)} />
            </div>
            <div className="relative">
              <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
                <code>{`docker pull ${meta.image_reference}`}</code>
              </pre>
              <CopyOutlined
                className="absolute top-3 right-3 cursor-pointer hover:text-blue-500"
                onClick={() => copy(`docker pull ${meta.image_reference}`)}
              />
            </div>
            <div className="relative">
              <pre className="bg-[var(--color-bg-5)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
                <code>docker load -i kubernetes-event-exporter.tar</code>
              </pre>
              <CopyOutlined
                className="absolute top-3 right-3 cursor-pointer hover:text-blue-500"
                onClick={() => copy('docker load -i kubernetes-event-exporter.tar')}
              />
            </div>
          </div>
        </div>

        <div>
          <div className="font-medium mb-2">4. {t('integration.renderedConfig')}</div>
          <Descriptions bordered size="small" column={1} labelStyle={{ width: 220 }}>
            <Descriptions.Item label="CLUSTER_NAME">
              {t('integration.clusterNameHelp')}
            </Descriptions.Item>
            <Descriptions.Item label="BK_LITE_RECEIVER_URL">
              <div className="flex items-center gap-2 break-all">
                <span>{meta.receiver_url}</span>
                <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copy(meta.receiver_url)} />
              </div>
            </Descriptions.Item>
            <Descriptions.Item label="BK_LITE_SECRET">
              <div className="flex items-center gap-2">
                <span>******************</span>
                <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => copy(source.secret)} />
              </div>
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

        <div>
          <div className="font-medium mb-2">5. {t('integration.applyToCluster')}</div>
          <div className="relative">
            <pre className="bg-[var(--color-bg-1)] p-2 pr-10 rounded border border-[var(--color-border-1)] text-[13px] font-mono leading-relaxed whitespace-pre-wrap break-all max-w-full">
              <code>kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml</code>
            </pre>
            <CopyOutlined
              className="absolute top-3 right-3 cursor-pointer hover:text-blue-500"
              onClick={() => copy('kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml')}
            />
          </div>
        </div>

        <div>
          <div className="font-medium mb-2">6. {t('integration.verifyResult')}</div>
          <div className="text-sm text-[var(--color-text-2)]">
            {t('integration.verifyResultHelp')}
          </div>
        </div>
      </div>

      <h4 className="mt-6 mb-2 font-medium pl-2 border-l-4 border-blue-400 inline-block leading-tight">
        {t('integration.k8sGuideNotes')}
      </h4>
      <div className="rounded border border-[var(--color-border-1)] bg-[var(--color-bg-5)] p-4 space-y-2">
        {meta.notes.map((note: string) => (
          <div key={note} className="text-sm text-[var(--color-text-2)]">
            • {note}
          </div>
        ))}
      </div>
    </div>
  );
};

export default K8sGuide;
