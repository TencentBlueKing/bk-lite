"use client";
import OperateModal from '@/components/operate-modal';
import { useState, useImperativeHandle, forwardRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Upload, Button, message, type UploadFile, type UploadProps, Switch } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { ModalConfig, ModalRef, TableData } from '@/app/mlops/types';
import { TrainDataParams } from '@/app/mlops/types/manage';
import usePlayroundApi from '../../api';
const { Dragger } = Upload;

interface UploadModalProps {
  onSuccess: () => void
}

const SampleManageModal = forwardRef<ModalRef, UploadModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const { createSampleFile } = usePlayroundApi();
  const [visiable, setVisiable] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [fileList, setFileList] = useState<UploadFile<any>[]>([]);
  const [checked, setChecked] = useState<boolean>(false);
  const [formData, setFormData] = useState<TableData>();

  useImperativeHandle(ref, () => ({
    showModal: ({ form }: ModalConfig) => {
      setVisiable(true);
      setFormData(form);
    }
  }));

  const handleChange: UploadProps['onChange'] = ({ fileList }) => {
    setFileList(fileList);
  };

  const props: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    fileList: fileList,
    onChange: handleChange,
    beforeUpload: (file) => {
      const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
      if (!isCSV) {
        message.warning(t('datasets.uploadWarn'))
      }
      return isCSV;
    },
    accept: '.csv'
  };

  const handleFileRead = (text: string) => {
    // 统一换行符为 \n
    const lines = text.replace(/\r\n|\r|\n/g, '\n')?.split('\n').filter(line => line.trim() !== '');
    if (!lines.length) return [];
    console.log(formData?.categoryType, formData)
    const headers = formData?.categoryType !== 'classification' ? ['timestamp', 'value', 'label'] : lines[0].split(',');
    console.log(headers);
    const data = lines.slice(1).map((line, index) => {
      const values = line.split(',');
      return headers.reduce((obj: Record<string, any>, key, idx) => {
        const value = values[idx];
        if (key === 'timestamp') {
          const timestamp = new Date(value).getTime();
          obj[key] = timestamp / 1000;
        } else {
          const numValue = Number(value);
          obj[key] = isNaN(numValue) ? value : numValue;
        }
        if (formData?.categoryType === 'anomaly_detection') {
          obj['index'] = index;
        }
        return obj;
      }, {});
    });
    return data as TrainDataParams[];
  };

  const handleSubmit = async () => {
    setConfirmLoading(true);
    try {
      const file: UploadFile<any> = fileList[0];
      if (!file?.originFileObj) {
        setConfirmLoading(false);
        return message.error(t('datasets.pleaseUpload'));
      }
      const [capability] = formData?.capability;
      const text = await file?.originFileObj.text();
      const data: TrainDataParams[] = handleFileRead(text);
      console.log(data);
      const train_data = data.map(item => {
        if (formData?.categoryType === 'anomaly_detection') {
          return { timestamp: item.timestamp, value: item.value }
        }
        return item
      });
      const params = {
        name: file.name,
        capability,
        train_data: train_data,
        is_active: checked,
      };
      await createSampleFile(params);
      setVisiable(false);
      message.success(t('datasets.uploadSuccess'));
      onSuccess();

    } catch (e) {
      console.log(e);
      message.error(t('common.error'))
    } finally {
      setConfirmLoading(false);
      setFileList([]);
    }
  };

  const handleCancel = () => {
    setVisiable(false);
    setFileList([]);
    setChecked(false);
  };

  const CheckedType = () => (
    <div className='text-left flex justify-between items-center'>
      <div className='flex-1'>
        <span className='leading-[32px] mr-2'>{t(`manage.isActive`) + ": "} </span>
        <Switch checked={checked} onChange={(checked) => setChecked(checked)} />
      </div>
      <Button key="submit" className='mr-2' loading={confirmLoading} type="primary" onClick={handleSubmit}>
        {t('common.confirm')}
      </Button>
      <Button key="cancel" onClick={handleCancel}>
        {t('common.cancel')}
      </Button>
    </div>
  );

  return (
    <OperateModal
      title={t(`datasets.upload`)}
      open={visiable}
      onCancel={() => handleCancel()}
      footer={[
        <CheckedType key="checked" />,
      ]}
    >
      <Dragger {...props}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{t('datasets.uploadText')}</p>
      </Dragger>
    </OperateModal>
  )
});

SampleManageModal.displayName = 'SampleManageModal';
export default SampleManageModal;