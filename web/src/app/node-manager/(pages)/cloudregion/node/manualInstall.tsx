'use client';

import React from 'react';
import { Button, Form, Select, Spin, Input } from 'antd';
import { TableDataItem } from '@/app/node-manager/types';
import { useTranslation } from '@/utils/i18n';
import CodeEditor from '@/app/node-manager/components/codeEditor';
import { DownloadOutlined } from '@ant-design/icons';
import controllerInstallSyle from './index.module.scss';

interface ManualInstallFormItemsProps {
  sidecarVersionList: TableDataItem[];
  sidecarPackageLoading: boolean;
  loadingCommand: boolean;
  script: string;
  groupList: Array<{ label: string; value: any }>;
  versionLoading?: boolean;
  selectedSidecar?: string;
  disabled?: boolean;
  onSidecarChange: (value: string) => void;
  onDownload: () => void;
}

const ManualInstallFormItems: React.FC<ManualInstallFormItemsProps> = ({
  sidecarVersionList,
  sidecarPackageLoading,
  loadingCommand,
  script,
  groupList,
  versionLoading = false,
  disabled = false,
  selectedSidecar,
  onSidecarChange,
  onDownload,
}) => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        label={t('node-manager.cloudregion.node.installationGuide')}
        className="mb-0"
      >
        <div className={`${controllerInstallSyle.description} mb-[16px]`}>
          {t('node-manager.cloudregion.node.downloadTips')}
        </div>
      </Form.Item>

      <div className="pl-[20px]">
        <Form.Item
          required
          label={t('node-manager.cloudregion.node.nodeName')}
          name="manual_node_name"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Input className="w-[500px]" />
        </Form.Item>

        <Form.Item
          required
          label={t('node-manager.cloudregion.node.ip')}
          name="manual_ip"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Input className="w-[500px]" />
        </Form.Item>

        <Form.Item
          required
          label={t('node-manager.cloudregion.node.group')}
          name="manual_organizations"
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Select
            mode="multiple"
            maxTagCount="responsive"
            allowClear
            showSearch
            style={{ width: 500 }}
            options={groupList}
            filterOption={(input, option) =>
              (option?.label || '').toLowerCase().includes(input.toLowerCase())
            }
          ></Select>
        </Form.Item>
        <Form.Item
          required
          label={t('node-manager.cloudregion.node.sidecarVersion')}
          className="flex items-center"
        >
          <Form.Item
            name="manual_sidecar"
            noStyle
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              style={{ width: 500 }}
              showSearch
              allowClear
              value={selectedSidecar}
              placeholder={t('common.pleaseSelect')}
              loading={versionLoading}
              disabled={disabled}
              options={sidecarVersionList.map((item) => ({
                value: item.id,
                label: item.version,
              }))}
              filterOption={(input, option) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              onChange={onSidecarChange}
            />
          </Form.Item>
          <Button
            type="link"
            icon={<DownloadOutlined />}
            disabled={!selectedSidecar}
            loading={sidecarPackageLoading}
            onClick={onDownload}
          >
            {t('node-manager.cloudregion.node.downloadPackage')}
          </Button>
        </Form.Item>
      </div>

      <div className={`${controllerInstallSyle.description} mb-[16px]`}>
        {t('node-manager.cloudregion.node.scriptTips')}
      </div>

      <Spin className="w-full" spinning={loadingCommand}>
        <CodeEditor
          readOnly
          showCopy
          value={script}
          className="ml-[20px] mb-[16px]"
          width="100%"
          height={200}
          mode="python"
          theme="monokai"
          name="editor"
        />
      </Spin>

      <div className={`${controllerInstallSyle.description}`}>
        {t('node-manager.cloudregion.node.finishTips')}
      </div>
    </>
  );
};

export default ManualInstallFormItems;
