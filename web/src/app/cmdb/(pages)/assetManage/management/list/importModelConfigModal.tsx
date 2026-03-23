'use client';

import React, { useState, forwardRef, useImperativeHandle, useRef, useEffect } from 'react';
import { Button, message, Upload } from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import type { UploadProps } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { useAuth } from '@/context/auth';
import { useSession } from 'next-auth/react';

interface ImportModelConfigModalProps {
  onSuccess: () => void;
}

export interface ImportModelConfigModalRef {
  showModal: () => void;
}

const ImportModelConfigModal = forwardRef<ImportModelConfigModalRef, ImportModelConfigModalProps>(
  ({ onSuccess }, ref) => {
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [exportDisabled, setExportDisabled] = useState<boolean>(false);
    const [fileList, setFileList] = useState<any[]>([]);
    const { t } = useTranslation();
    const { importModelConfig, exportModelConfig } = useModelApi();
    const { Dragger } = Upload;
    const authContext = useAuth();
    const { data: session } = useSession();
    const token = (session?.user as any)?.token || authContext?.token || null;
    const tokenRef = useRef(token);

    useEffect(() => {
      tokenRef.current = token;
    }, [token]);

    useImperativeHandle(ref, () => ({
      showModal: () => {
        setVisible(true);
        setFileList([]);
      },
    }));

    const exportTemplate = async () => {
      try {
        setExportDisabled(true);
        await exportModelConfig(tokenRef.current);
      } catch (error: any) {
        message.error(error.message);
      } finally {
        setExportDisabled(false);
      }
    };

    const handleChange: UploadProps['onChange'] = ({ fileList }) => {
      setFileList(fileList);
    };

    const customRequest = async (options: any) => {
      const { onSuccess: uploadSuccess } = options;
      uploadSuccess('Ok');
    };

    const operateImport = async () => {
      try {
        setConfirmLoading(true);
        await importModelConfig(fileList[0].originFileObj, tokenRef.current);
        message.success(t('Model.importSuccess'));
        onSuccess();
        handleCancel();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
      setFileList([]);
    };

    return (
      <OperateModal
        title={t('Model.importModelConfig')}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={confirmLoading}
              disabled={fileList.length === 0}
              onClick={operateImport}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <div>
          <Dragger
            customRequest={customRequest}
            onChange={handleChange}
            fileList={fileList}
            accept=".xls,.xlsx"
            maxCount={1}
            className="w-full"
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{t('uploadAction')}</p>
            <p className="ant-upload-hint">{t('Model.uploadDescription')}</p>
          </Dragger>
          <Button
            disabled={exportDisabled}
            className="mt-[10px]"
            type="link"
            onClick={exportTemplate}
          >
            {t('exportTemplate')}
          </Button>
        </div>
      </OperateModal>
    );
  }
);

ImportModelConfigModal.displayName = 'ImportModelConfigModal';
export default ImportModelConfigModal;
