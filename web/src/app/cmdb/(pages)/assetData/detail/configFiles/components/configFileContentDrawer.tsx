'use client';

import { Button, Select, Space, Typography } from 'antd';
import CodeSnippet from '@/components/code-snippet';
import ContentFormDrawer from '@/components/content-form-drawer';
import type {
  ConfigFileContentResponse,
  ConfigFileItem,
} from '@/app/cmdb/types/configFile';
import { useTranslation } from '@/utils/i18n';

const { Text } = Typography;

const ENCODING_OPTIONS = [
  { label: 'UTF-8', value: 'utf-8' },
  { label: 'GBK', value: 'gbk' },
  { label: 'GB18030', value: 'gb18030' },
  { label: 'Big5', value: 'big5' },
  { label: 'Shift_JIS', value: 'shift_jis' },
  { label: 'UTF-16LE', value: 'utf-16le' },
];

interface ConfigFileContentDrawerProps {
  open: boolean;
  loading: boolean;
  activeFile: ConfigFileItem | null;
  activeVersionLabel: string;
  contentData: ConfigFileContentResponse | null;
  contentEncoding: string;
  onClose: () => void;
  onEncodingChange: (encoding: string) => void;
  onCopy: () => void;
}

const ConfigFileContentDrawer = ({
  open,
  loading,
  activeFile,
  activeVersionLabel,
  contentData,
  contentEncoding,
  onClose,
  onEncodingChange,
  onCopy,
}: ConfigFileContentDrawerProps) => {
  const { t } = useTranslation();

  return (
    <ContentFormDrawer
      open={open}
      loading={loading}
      title={
        activeFile
          ? `${t('ConfigFile.fileContentTitle')} · ${activeFile.file_name}${activeVersionLabel ? ` · ${activeVersionLabel}` : ''}`
          : t('ConfigFile.fileContentTitle')
      }
      width={760}
      onClose={onClose}
      hideFooter
      extra={
        <Space>
          <Button onClick={onCopy}>{t('ConfigFile.copyContent')}</Button>
          <Text type="secondary">{t('ConfigFile.encoding')}</Text>
          <Select
            value={contentEncoding}
            options={ENCODING_OPTIONS}
            style={{ width: 130 }}
            onChange={onEncodingChange}
          />
        </Space>
      }
    >
      <Space direction="vertical" size={12} className="w-full">
        <div className="rounded-lg bg-[var(--color-fill-1)] p-3">
          <div>
            <Text type="secondary">{t('ConfigFile.configFileName')}</Text>
            {activeFile?.file_name || '--'}
          </div>
          <div>
            <Text type="secondary">{t('ConfigFile.configFilePath')}</Text>
            {activeFile?.file_path || '--'}
          </div>
          <div>
            <Text type="secondary">{t('ConfigFile.configFileVersion')}</Text>
            {activeFile?.latest_version || '--'}
          </div>
        </div>
        <CodeSnippet
          value={contentData?.content || t('ConfigFile.noContent')}
          tone="inverse"
          maxHeight="calc(100vh - 240px)"
          className="!rounded-lg !px-4 !py-4"
        />
      </Space>
    </ContentFormDrawer>
  );
};

export default ConfigFileContentDrawer;
