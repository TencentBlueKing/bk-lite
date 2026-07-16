'use client';

import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Form, type FormInstance, Input, message, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateFormModal from '@/components/operate-form-modal';
import { DatasetType } from '@/components/mlops-shared';
import type { MlopsDatasetModalRef } from '@/components/mlops-dataset-shared/contracts';

interface DatasetReleaseFile {
  id: number;
  name: string;
  is_train_data: boolean;
  is_val_data: boolean;
  is_test_data: boolean;
}

interface DatasetReleasePayload {
  dataset: number;
  version: string;
  train_file_id: number;
  val_file_id: number;
  test_file_id: number;
}

interface DatasetReleaseModalProps {
  datasetId: string;
  datasetType: DatasetType;
  onSuccess?: () => void;
  fetchDatasetFiles: (params: {
    datasetId: string;
    datasetType: DatasetType;
  }) => Promise<DatasetReleaseFile[]>;
  createDatasetRelease: (
    datasetType: DatasetType,
    payload: DatasetReleasePayload,
  ) => Promise<void>;
}

const DatasetReleaseModal = forwardRef<MlopsDatasetModalRef, DatasetReleaseModalProps>(
  (
    {
      datasetId,
      datasetType,
      onSuccess,
      fetchDatasetFiles,
      createDatasetRelease,
    },
    ref,
  ) => {
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [open, setOpen] = useState(false);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [trainFiles, setTrainFiles] = useState<DatasetReleaseFile[]>([]);
    const [valFiles, setValFiles] = useState<DatasetReleaseFile[]>([]);
    const [testFiles, setTestFiles] = useState<DatasetReleaseFile[]>([]);

    const splitFileOptions = useMemo(
      () => ({
        train: trainFiles.map((file) => ({ label: file.name, value: file.id })),
        val: valFiles.map((file) => ({ label: file.name, value: file.id })),
        test: testFiles.map((file) => ({ label: file.name, value: file.id })),
      }),
      [testFiles, trainFiles, valFiles],
    );

    useImperativeHandle(ref, () => ({
      showModal() {
        setOpen(true);
        void fetchFiles();
      },
    }));

    const fetchFiles = async () => {
      try {
        const items = await fetchDatasetFiles({ datasetId, datasetType });

        setTrainFiles(items.filter((item) => item.is_train_data));
        setValFiles(items.filter((item) => item.is_val_data));
        setTestFiles(items.filter((item) => item.is_test_data));
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
        message.error(t('common.fetchFailed'));
      }
    };

    const handleCancel = () => {
      setOpen(false);
      formRef.current?.resetFields();
    };

    const handleSubmit = async () => {
      setConfirmLoading(true);
      try {
        const values = await formRef.current?.validateFields();

        await createDatasetRelease(datasetType, {
          dataset: Number(datasetId),
          ...values,
        });

        message.success(t('common.publishSuccess'));
        setOpen(false);
        formRef.current?.resetFields();
        onSuccess?.();
      } catch (error: any) {
        console.error(`${t('mlops-common.publishFailed')}:`, error);
        message.error(
          `${t('mlops-common.publishFailed')}:${error?.response?.data?.error || error.message}`,
        );
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <OperateFormModal
        title={t('common.publish')}
        open={open}
        onCancel={handleCancel}
        width={700}
        confirmText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={confirmLoading}
        onConfirm={handleSubmit}
      >
        <Form ref={formRef} layout="vertical">
          <Form.Item
            name="version"
            label={t('common.version')}
            rules={[
              { required: true, message: t('mlops-common.inputVersionMsg') },
              { pattern: /^v\d+\.\d+\.\d+$/, message: 'type: v1.0.0' },
            ]}
          >
            <Input placeholder={t('mlops-common.versionIptMsg')} />
          </Form.Item>

          <Form.Item
            name="train_file_id"
            label={t('mlops-common.trainfile')}
            rules={[{ required: true, message: t('mlops-common.selectTrainfile') }]}
          >
            <Select
              placeholder={t('mlops-common.selectTrainfile')}
              options={splitFileOptions.train}
            />
          </Form.Item>

          <Form.Item
            name="val_file_id"
            label={t('mlops-common.valfile')}
            rules={[{ required: true, message: t('mlops-common.selectValfile') }]}
          >
            <Select
              placeholder={t('mlops-common.selectValfile')}
              options={splitFileOptions.val}
            />
          </Form.Item>

          <Form.Item
            name="test_file_id"
            label={t('mlops-common.testfile')}
            rules={[{ required: true, message: t('mlops-common.selectTestfile') }]}
          >
            <Select
              placeholder={t('mlops-common.selectTestfile')}
              options={splitFileOptions.test}
            />
          </Form.Item>
        </Form>
      </OperateFormModal>
    );
  },
);

DatasetReleaseModal.displayName = 'DatasetReleaseModal';

export type { DatasetReleaseFile, DatasetReleaseModalProps, DatasetReleasePayload };
export default DatasetReleaseModal;
