'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button, message, Upload } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import { ModalRef, ModalConfig } from '@/app/monitor/types';
import type { UploadProps } from 'antd';
import { InboxOutlined } from '@ant-design/icons';

const ImportModal = forwardRef<ModalRef, ModalConfig>(({ onSuccess }, ref) => {
  const [groupVisible, setGroupVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [title, setTitle] = useState<string>('');
  const [fileList, setFileList] = useState<any[]>([]);
  const [parsedData, setParsedData] = useState<any>(null); // 新增状态用于存储解析后的数据
  const { t } = useTranslation();
  const { importMonitorPlugin } = useIntegrationApi();
  const { Dragger } = Upload;

  useImperativeHandle(ref, () => ({
    showModal: ({ title }) => {
      // 开启弹窗的交互
      setGroupVisible(true);
      setTitle(title);
      setFileList([]);
      setParsedData(null); // 重置解析后的数据
    },
  }));

  const handleSubmit = () => {
    operateAttr();
  };

  const handleChange: UploadProps['onChange'] = ({ fileList }) => {
    setFileList(fileList);
  };

  const customRequest = async (options: any) => {
    const { file, onSuccess: onHandleSuccess } = options;
    // 解析文件
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const json = JSON.parse(reader.result as string);
        setParsedData(json); // 存储解析后的数据
        onHandleSuccess('Ok');
      } catch {
        setParsedData(null);
        message.error('Failed to parse JSON file');
      }
    };
    reader.readAsText(file);
  };

  const operateAttr = async () => {
    try {
      setConfirmLoading(true);
      await importMonitorPlugin(parsedData);
      message.success(t('common.successfullyImported'));
      onSuccess();
      handleCancel();
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    setGroupVisible(false);
    setParsedData(null);
  };

  return (
    <div>
      <OperateModal
        title={title}
        visible={groupVisible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              disabled={!parsedData}
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Dragger
          customRequest={customRequest}
          onChange={handleChange}
          fileList={fileList}
          accept=".json"
          maxCount={1}
          className="w-full"
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">{t('common.uploadAction')}</p>
          <p className="ant-upload-hint">
            {t('monitor.integrations.groupImportTips')}
          </p>
        </Dragger>
      </OperateModal>
    </div>
  );
});

ImportModal.displayName = 'importModal';
export default ImportModal;
