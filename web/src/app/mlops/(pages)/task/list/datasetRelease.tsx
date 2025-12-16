"use client";
import { ModalRef } from '@/app/mlops/types';
import OperateModal from '@/components/operate-modal';
import { Form, FormInstance, Button, Input, message, Alert } from 'antd';
import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';

const { TextArea } = Input;

interface DatasetReleaseModalProps {
  activeTag: string[]
}

const DatasetReleaseModal = forwardRef<ModalRef, DatasetReleaseModalProps>(({ activeTag }, ref) => {
  const { t } = useTranslation();
  const { datasetRelease } = useMlopsTaskApi();
  const formRef = useRef<FormInstance>(null);
  const [open, setOpen] = useState<boolean>(false);
  const [confirmState, setConfirmState] = useState<boolean>(false);
  const [formData, setFormData] = useState<any>(null);
  const [releaseResult, setReleaseResult] = useState<any>(null);

  useImperativeHandle(ref, () => ({
    showModal(data) {
      setOpen(true);
      setFormData(data);
      setReleaseResult(null);
    },
  }));

  const handleCancel = () => {
    setOpen(false);
    formRef.current?.resetFields();
    setReleaseResult(null);
  };

  const handleSubmit = async () => {
    const [key] = activeTag;
    if (key !== 'timeseries_predict') {
      message.warning('当前仅支持时间序列预测数据集发布');
      return;
    }
    
    setConfirmState(true);
    try {
      if (formData) {
        const values = await formRef.current?.validateFields();
        const result = await datasetRelease(formData?.id, values);
        
        setReleaseResult(result);
        message.success('数据集发布成功');
        
        // 显示结果 2 秒后关闭
        setTimeout(() => {
          setOpen(false);
          formRef.current?.resetFields();
        }, 2000);
      }
    } catch (e: any) {
      console.log(e);
      message.error('数据集发布失败: ' + (e?.response?.data?.error || e.message))
    } finally {
      setConfirmState(false);
    }
  };


  return (
    <>
      <OperateModal
        title={'数据集版本发布'}
        open={open}
        onCancel={handleCancel}
        width={600}
        footer={[
          <Button key="submit" loading={confirmState} type="primary" onClick={handleSubmit}>
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

          <Form.Item
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
          </Form.Item>
        </Form>

        {releaseResult && (
          <Alert
            message="发布成功"
            description={
              <div>
                <p>版本号: {releaseResult.version}</p>
                <p>数据集: {releaseResult.dataset_name}</p>
                <p>文件大小: {(releaseResult.file_size / 1024 / 1024).toFixed(2)} MB</p>
                {releaseResult.metadata && (
                  <p>样本数: 训练{releaseResult.metadata.train_samples} / 验证{releaseResult.metadata.val_samples} / 测试{releaseResult.metadata.test_samples}</p>
                )}
              </div>
            }
            type="success"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </OperateModal>
    </>
  )
});

DatasetReleaseModal.displayName = "DatasetReleaseModal";

export default DatasetReleaseModal;