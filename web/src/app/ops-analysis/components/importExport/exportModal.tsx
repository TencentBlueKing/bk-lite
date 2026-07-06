import React, { useState } from 'react';
import { Modal, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useImportExportApi, ObjectType } from '../../api/importExport';

export interface ExportModalProps {
  visible: boolean;
  onCancel: () => void;
  objectType: ObjectType;
  objectId: number;
  objectName: string;
}

const ExportModal: React.FC<ExportModalProps> = ({
  visible,
  onCancel,
  objectType,
  objectId,
  objectName,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const { exportObjects, downloadYaml } = useImportExportApi();

  const handleOk = async () => {
    try {
      setLoading(true);

      const response = await exportObjects({
        object_type: objectType,
        object_ids: [objectId],
      });

      if (response.yaml_content) {
        downloadYaml(response.yaml_content, `${objectName}_export`);
        message.success(t('opsAnalysisSidebar.exportSuccess'));
        onCancel();
      }
    } catch (error: any) {
      message.error(error?.message || t('opsAnalysisSidebar.exportFailed'));
      console.error('Export failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    onCancel();
  };

  return (
    <Modal
      title={t('opsAnalysisSidebar.exportYaml')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={560}
      destroyOnHidden
      centered
    >
      <div className="py-2">
        <div className="mb-4 px-1 py-1">
          <div className="text-[15px] leading-6 text-[rgba(0,0,0,0.88)]">
            {t('opsAnalysisSidebar.exportConfirmMsg')}
            <span className="mx-1 font-semibold break-all">{objectName}</span>
            ?
          </div>
          <div className="mt-1 text-sm leading-6 text-[rgba(0,0,0,0.65)]">
            {t('opsAnalysisSidebar.includeDependencies')}
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default ExportModal;
