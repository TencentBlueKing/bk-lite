'use client';

import React, { useState } from 'react';
import { Alert, Button, Collapse, Descriptions, Space } from 'antd';
import CodeEditor from '@/components/code-editor';
import useIntegrationApi from '@/app/monitor/api/integration';
import { useTranslation } from '@/utils/i18n';
import type {
  K3sCommandData,
  K3sVerificationResult,
} from '@/app/monitor/types/integration';
import CommonIssuesDrawer from './commonIssuesDrawer';

interface CollectorInstallProps {
  commandData: K3sCommandData | null;
  onPrev: () => void;
  onNext: () => void;
}

const CollectorInstall: React.FC<CollectorInstallProps> = ({
  commandData,
  onPrev,
  onNext,
}) => {
  const { t } = useTranslation();
  const { verifyK3sReporting } = useIntegrationApi();
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] =
    useState<K3sVerificationResult | null>(null);
  const [issuesOpen, setIssuesOpen] = useState(false);

  const verify = async () => {
    if (!commandData) return;
    setVerifying(true);
    try {
      const result = await verifyK3sReporting(commandData.instance_id);
      setVerification(result);
      if (result.status === 'success') {
        onNext();
      }
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-5">
      <Alert
        type="info"
        showIcon
        message={t('monitor.integrations.k3s.installCommandDesc')}
      />
      <CodeEditor
        mode="shell"
        theme="monokai"
        name="k3s-install-command"
        width="100%"
        height="120px"
        readOnly
        value={commandData?.install_command || ''}
        headerOptions={{ copy: true }}
      />
      <Collapse
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'uninstall',
            label: t('monitor.integrations.k3s.uninstallCommand'),
            children: (
              <CodeEditor
                mode="shell"
                theme="monokai"
                name="k3s-uninstall-command"
                width="100%"
                height="120px"
                readOnly
                value={commandData?.uninstall_command || ''}
                headerOptions={{ copy: true }}
              />
            ),
          },
        ]}
      />
      {verification ? (
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label={t('monitor.integrations.k3s.signalCluster')}>
            {verification.signals.cluster.status}
          </Descriptions.Item>
          <Descriptions.Item label={t('monitor.integrations.k3s.signalContainer')}>
            {verification.signals.container.status}
          </Descriptions.Item>
          <Descriptions.Item label={t('monitor.integrations.k3s.signalNode')}>
            {verification.signals.node.status}
          </Descriptions.Item>
        </Descriptions>
      ) : null}
      <Space>
        <Button onClick={onPrev}>{t('common.pre')}</Button>
        <Button type="primary" loading={verifying} onClick={verify}>
          {t('monitor.integrations.k3s.verify')}
        </Button>
        <Button onClick={() => setIssuesOpen(true)}>
          {t('monitor.integrations.k3s.commonIssues')}
        </Button>
      </Space>
      <CommonIssuesDrawer
        open={issuesOpen}
        onClose={() => setIssuesOpen(false)}
      />
    </div>
  );
};

export default CollectorInstall;
