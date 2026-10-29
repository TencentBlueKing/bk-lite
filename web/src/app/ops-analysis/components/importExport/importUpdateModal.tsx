import React, { useState } from 'react';
import { Alert, Modal, Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import { useImportExportApi, type ImportUpdateResponse } from '../../api/importExport';

const { Dragger } = Upload;

export interface ImportUpdateModalProps {
  visible: boolean;
  onCancel: () => void;
  objectType: CanvasType;
  objectId: number;
  objectName: string;
  beforeSubmit?: () => boolean | Promise<boolean>;
  onSuccess?: (result: ImportUpdateResponse) => void | Promise<void>;
}

const ImportUpdateModal: React.FC<ImportUpdateModalProps> = ({
  visible,
  onCancel,
  objectType,
  objectId,
  objectName,
  beforeSubmit,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { importUpdateCanvas } = useImportExportApi();
  const [loading, setLoading] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [fileName, setFileName] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const resetState = () => {
    setLoading(false);
    setYamlContent('');
    setFileName('');
    setErrorMessage('');
  };

  const handleCancel = () => {
    resetState();
    onCancel();
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    showUploadList: false,
    beforeUpload: (file) => {
      const isYaml =
        file.name.endsWith('.yaml') ||
        file.name.endsWith('.yml') ||
        file.type === 'text/yaml' ||
        file.type === 'application/x-yaml';
      if (!isYaml) {
        message.error(t('opsAnalysisSidebar.importInvalidFileType'));
        return Upload.LIST_IGNORE;
      }
      const isLt2M = file.size / 1024 / 1024 < 2;
      if (!isLt2M) {
        message.error(t('opsAnalysisSidebar.importFileTooLarge'));
        return Upload.LIST_IGNORE;
      }
      return false;
    },
    onChange: async (info) => {
      const file = info.fileList[0]?.originFileObj;
      if (!file) {
        setYamlContent('');
        setFileName('');
        return;
      }
      setErrorMessage('');
      setFileName(file.name);
      setYamlContent(await file.text());
    },
  };

  const handleOk = async () => {
    if (!yamlContent.trim()) {
      setErrorMessage(t('opsAnalysisSidebar.importInvalidFileType'));
      return;
    }
    if (beforeSubmit && !(await beforeSubmit())) {
      return;
    }
    setLoading(true);
    setErrorMessage('');
    try {
      const result = await importUpdateCanvas({
        object_type: objectType,
        object_id: objectId,
        yaml_content: yamlContent,
      });
      message.success(t('opsAnalysisSidebar.importUpdateSuccess'));
      resetState();
      await onSuccess?.(result);
    } catch (error) {
      const fallback = t('opsAnalysisSidebar.importUpdateFailed');
      setErrorMessage(error instanceof Error && error.message ? error.message : fallback);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={t('opsAnalysisSidebar.importUpdate')}
      open={visible}
      onOk={() => void handleOk()}
      onCancel={handleCancel}
      confirmLoading={loading}
      okButtonProps={{ disabled: !yamlContent.trim() }}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={560}
      destroyOnHidden
      centered
    >
      <div className="py-2">
        <div className="mb-4 px-1 py-1">
          <div className="text-[15px] leading-6 text-[var(--color-text-1)]">
            {t('opsAnalysisSidebar.importUpdateOverwrite')}
            <span className="mx-1 font-semibold break-all">{objectName}</span>
          </div>
          <div className="mt-1 text-sm leading-6 text-[var(--color-text-2)]">
            {t('opsAnalysisSidebar.importUpdateHint')}
          </div>
        </div>
        <Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">{t('opsAnalysisSidebar.importUploadText')}</p>
          <p className="ant-upload-hint">
            {fileName || t('opsAnalysisSidebar.importUploadHint')}
          </p>
        </Dragger>
        {errorMessage ? (
          <Alert className="mt-3" type="error" showIcon message={errorMessage} />
        ) : null}
      </div>
    </Modal>
  );
};

export default ImportUpdateModal;
