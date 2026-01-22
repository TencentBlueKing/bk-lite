"use client";
import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Form, FormInstance, Button, Input, message, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useMlopsManageApi from '@/app/mlops/api/manage';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { DatasetReleaseKey, ModalRef } from '@/app/mlops/types';

// const { TextArea } = Input;

interface DatasetReleaseModalProps {
  datasetId: string;
  datasetType: DatasetReleaseKey;
  onSuccess?: () => void;
}

interface TrainDataFile {
  id: number;
  name: string;
  is_train_data: boolean;
  is_val_data: boolean;
  is_test_data: boolean;
}

const DatasetReleaseModal = forwardRef<ModalRef, DatasetReleaseModalProps>(
  ({ datasetId, datasetType, onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getTrainDataByDataset } = useMlopsManageApi();
    const taskApi = useMlopsTaskApi();
    const formRef = useRef<FormInstance>(null);
    const [open, setOpen] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [trainFiles, setTrainFiles] = useState<TrainDataFile[]>([]);
    const [valFiles, setValFiles] = useState<TrainDataFile[]>([]);
    const [testFiles, setTestFiles] = useState<TrainDataFile[]>([]);

    useImperativeHandle(ref, () => ({
      showModal() {
        setOpen(true);
        fetchFiles();
      },
    }));

    const fetchFiles = async () => {
      try {
        const { items } = await getTrainDataByDataset({
          key: datasetType,
          dataset: datasetId,
          page: 1,
          page_size: 1000,
        });

        const train = items?.filter((item: TrainDataFile) => item.is_train_data) || [];
        const val = items?.filter((item: TrainDataFile) => item.is_val_data) || [];
        const test = items?.filter((item: TrainDataFile) => item.is_test_data) || [];

        setTrainFiles(train);
        setValFiles(val);
        setTestFiles(test);
      } catch (error) {
        console.error(t(`common.fetchFailed`), error);
        message.error(t(`common.fetchFailed`));
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

        await taskApi.createDatasetRelease(
          datasetType,
          {
            dataset: parseInt(datasetId),
            ...values,
          }
        );

        message.success(t(`common.publishSuccess`));
        setOpen(false);
        formRef.current?.resetFields();
        onSuccess?.();
      } catch (error: any) {
        console.error(t(`mlops-common.publishFailed`) + ':', error);
        message.error(t(`mlops-common.publishFailed`) + ':' + (error?.response?.data?.error || error.message));
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <OperateModal
        title={t(`common.publish`)}
        open={open}
        onCancel={handleCancel}
        width={700}
        footer={[
          <Button key="submit" loading={confirmLoading} type="primary" onClick={handleSubmit}>
            {t('common.confirm')}
          </Button>,
          <Button key="cancel" onClick={handleCancel}>
            {t('common.cancel')}
          </Button>,
        ]}
      >
        <Form ref={formRef} layout="vertical">
          <Form.Item
            name="version"
            label={t(`common.version`)}
            rules={[
              { required: true, message: t(`mlops-common.inputVersionMsg`) },
              { pattern: /^v\d+\.\d+\.\d+$/, message: 'type: v1.0.0' }
            ]}
          >
            <Input placeholder={t(`mlops-common.versionIptMsg`)} />
          </Form.Item>

          <Form.Item
            name="train_file_id"
            label={t(`mlops-common.trainfile`)}
            rules={[
              { required: true, message: t(`mlops-common.selectTrainfile`) }
            ]}
          >
            <Select
              placeholder={t(`mlops-common.selectTrainfile`)}
              style={{ width: '100%' }}
              options={trainFiles.map(file => ({ label: file.name, value: file.id }))}
            />
          </Form.Item>

          <Form.Item
            name="val_file_id"
            label={t(`mlops-common.valfile`)}
            rules={[
              { required: true, message: t(`mlops-common.selectValfile`) }
            ]}
          >
            <Select
              placeholder={t(`mlops-common.selectValfile`)}
              style={{ width: '100%' }}
              options={valFiles.map(file => ({ label: file.name, value: file.id }))}
            />
          </Form.Item>

          <Form.Item
            name="test_file_id"
            label={t(`mlops-common.testfile`)}
            rules={[
              { required: true, message: t(`mlops-common.selectTestfile`) }
            ]}
          >
            <Select
              placeholder={t(`mlops-common.selectTestfile`)}
              style={{ width: '100%' }}
              options={testFiles.map(file => ({ label: file.name, value: file.id }))}
            />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

DatasetReleaseModal.displayName = "DatasetReleaseModal";

export default DatasetReleaseModal;
