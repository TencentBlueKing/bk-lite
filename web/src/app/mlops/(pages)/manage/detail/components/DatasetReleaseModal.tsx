"use client";
import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Form, FormInstance, Button, Input, message, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useMlopsManageApi from '@/app/mlops/api/manage';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { ModalRef } from '@/app/mlops/types';

// const { TextArea } = Input;

interface DatasetReleaseModalProps {
  datasetId: string;
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
  ({ datasetId, onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getTimeSeriesPredictTrainData } = useMlopsManageApi();
    const { createDatasetRelease } = useMlopsTaskApi();
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
        const { items } = await getTimeSeriesPredictTrainData({
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
        console.error('获取文件列表失败:', error);
        message.error('获取文件列表失败');
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

        const result = await createDatasetRelease({
          dataset: parseInt(datasetId),
          ...values,
        });

        message.success('数据集发布成功');
        console.log('发布结果:', result);

        setOpen(false);
        formRef.current?.resetFields();
        onSuccess?.();
      } catch (error: any) {
        console.error('数据集发布失败:', error);
        message.error('数据集发布失败: ' + (error?.response?.data?.error || error.message));
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <OperateModal
        title="发布数据集版本"
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
            label="版本号"
            rules={[
              { required: true, message: '请输入版本号' },
              { pattern: /^v\d+\.\d+\.\d+$/, message: '版本号格式: v1.0.0' }
            ]}
          >
            <Input placeholder="请输入语义化版本号，例如: v1.0.0" />
          </Form.Item>

          {/* <Form.Item
            name="name"
            label="版本名称（可选）"
          >
            <Input placeholder="如不填写，将自动生成" />
          </Form.Item>

          <Form.Item
            name="description"
            label="版本描述（可选）"
          >
            <TextArea
              rows={3}
              placeholder="描述此版本的主要变更内容..."
              maxLength={500}
              showCount
            />
          </Form.Item> */}

          <Form.Item
            name="train_file_id"
            label="训练文件"
            rules={[
              { required: true, message: '请选择一个训练文件' }
            ]}
          >
            <Select
              // mode="multiple"
              placeholder="选择训练数据文件"
              style={{ width: '100%' }}
              options={trainFiles.map(file => ({ label: file.name, value: file.id }))}
            />
          </Form.Item>

          <Form.Item
            name="val_file_id"
            label="验证文件"
            rules={[
              { required: true, message: '请选择一个验证文件' }
            ]}
          >
            <Select
              // mode="multiple"
              placeholder="选择验证数据文件"
              style={{ width: '100%' }}
              options={valFiles.map(file => ({ label: file.name, value: file.id }))}
            />
          </Form.Item>

          <Form.Item
            name="test_file_id"
            label="测试文件"
            rules={[
              { required: true, message: '请选择一个测试文件' }
            ]}
          >
            <Select
              // mode="multiple"
              placeholder="选择测试数据文件"
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
