import React, { useState, useEffect } from 'react';
import { Tabs, Spin, Result } from 'antd';
import MarkdownRenderer from '@/components/markdown';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import { getClientIdFromRoute } from '@/utils/route';

const { TabPane } = Tabs;

interface VersionModalProps {
  visible: boolean;
  onClose: () => void;
}

const VersionModal: React.FC<VersionModalProps> = ({ visible, onClose }) => {
  const { t } = useTranslation();
  const [activeKey, setActiveKey] = useState<string>('');
  const [versionFiles, setVersionFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const locale = typeof window !== 'undefined' && localStorage.getItem('locale');

  useEffect(() => {
    if (visible) {
      const routeClientId = getClientIdFromRoute();
      fetch(`/api/versions?locale=${locale}&clientId=${routeClientId}`)
        .then(res => res.json())
        .then(data => {
          const files = data.versionFiles || [];
          setVersionFiles(files);
          setLoading(false);
          if (files.length > 0) {
            setActiveKey(files[0]);
          }
        })
        .catch(() => {
          setVersionFiles([]);
          setLoading(false);
        });
    }
  }, [visible]);

  const handleTabChange = (key: string) => {
    setActiveKey(key);
  };

  return (
    <OperateModal
      visible={visible}
      title={t('common.version')}
      footer={null}
      onCancel={onClose}
      destroyOnClose
      width={900}
      styles={{ body: { overflowY: 'auto', height: 'calc(80vh - 108px)' } }}
    >
      {loading ? (
        <div className="min-h-[200px] flex items-center justify-center">
          <Spin tip="Loading..." />
        </div>
      ) : versionFiles.length === 0 ? (
        <Result
          status="info"
          title={t('common.noVersionLogs')}
        />
      ) : (
        <Tabs
          tabPosition="left"
          activeKey={activeKey}
          onChange={handleTabChange}
          className="h-full"
        >
          {versionFiles.map((versionFile) => (
            <TabPane tab={versionFile} key={versionFile}>
              <div className="p-4 overflow-y-auto h-full">
                {activeKey === versionFile && (
                  <MarkdownRenderer filePath="versions" fileName={versionFile} />
                )}
              </div>
            </TabPane>
          ))}
        </Tabs>
      )}
    </OperateModal>
  );
};

export default VersionModal;
