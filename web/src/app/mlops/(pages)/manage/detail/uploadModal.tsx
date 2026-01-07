import OperateModal from '@/components/operate-modal';
import { useState, useImperativeHandle, forwardRef, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { exportToCSV } from '@/app/mlops/utils/common';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Upload, Button, message, Checkbox, type UploadFile, type UploadProps, Input, Form, FormInstance } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { ModalConfig, ModalRef, TableData } from '@/app/mlops/types';
import { useSearchParams } from 'next/navigation';
const { Dragger } = Upload;

interface UploadModalProps {
  onSuccess: () => void
}

const SUPPORTED_UPLOAD_TYPES = [
  'anomaly_detection',
  'timeseries_predict',
  'image_classification',
  'object_detection',
  'log_clustering'
] as const;

const IMAGE_TYPES = ['image_classification', 'object_detection'];

const UploadModal = forwardRef<ModalRef, UploadModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const activeType = searchParams.get('activeTap') || '';
  const {
    addAnomalyTrainData,
    addTimeSeriesPredictTrainData,
    addImageClassificationTrainData,
    addObjectDetectionTrainData,
    addLogClusteringTrainData
  } = useMlopsManageApi();

  const UPLOAD_API: Record<string, (data: FormData) => Promise<any>> = {
    anomaly_detection: addAnomalyTrainData,
    timeseries_predict: addTimeSeriesPredictTrainData,
    image_classification: addImageClassificationTrainData,
    object_detection: addObjectDetectionTrainData,
    log_clustering: addLogClusteringTrainData,
  };

  const FILE_CONFIG: Record<string, { accept: string; maxCount: number; fileType: string }> = {
    anomaly_detection: { accept: '.csv', maxCount: 1, fileType: 'csv' },
    timeseries_predict: { accept: '.csv', maxCount: 1, fileType: 'csv' },
    image_classification: { accept: 'image/*', maxCount: 10, fileType: 'image' },
    object_detection: { accept: 'image/*', maxCount: 10, fileType: 'image' },
    log_clustering: { accept: '.txt', maxCount: 1, fileType: 'txt' },
  };

  const [visiable, setVisiable] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [fileList, setFileList] = useState<UploadFile<any>[]>([]);
  const [checkedType, setCheckedType] = useState<string[]>([]);
  const [selectTags, setSelectTags] = useState<{
    [key: string]: boolean
  }>({});
  const [formData, setFormData] = useState<TableData>();
  const formRef = useRef<FormInstance>(null)

  useImperativeHandle(ref, () => ({
    showModal: ({ form }: ModalConfig) => {
      setVisiable(true);
      setFormData(form);
    }
  }));

  const handleChange: UploadProps['onChange'] = ({ fileList }) => {
    setFileList(fileList);
  };

  const config = FILE_CONFIG[activeType];

  const props: UploadProps = {
    name: 'file',
    multiple: config?.fileType === 'image',
    maxCount: config?.maxCount || 1,
    fileList: fileList,
    onChange: handleChange,
    beforeUpload: (file) => {
      if (!config) return false;

      if (config.fileType === 'csv') {
        const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
        if (!isCSV) {
          message.warning(t('datasets.uploadWarn'));
        }
        return isCSV;
      } else if (config.fileType === 'txt') {
        const isTXT = file.type === "text/plain" || file.name.endsWith('.txt');
        if (!isTXT) {
          message.warning(t('datasets.uploadTxtWarn'));
        }
        return isTXT;
      } else if (config.fileType === 'image') {
        const isLt2M = file.size / 1024 / 1024 < 2;
        if (!isLt2M) {
          message.error(t('datasets.over2MB'));
        }
        return isLt2M || Upload.LIST_IGNORE;
      }
      return true;
    },
    accept: config?.accept || '.csv',
  };

  const onSelectChange = (value: string[]) => {
    setCheckedType(value);
    const object = value.reduce((prev: Record<string, boolean>, current: string) => {
      return {
        ...prev,
        [current]: true
      };
    }, {});
    setSelectTags(object);
  };

  const validateFileUpload = (): UploadFile[] | null => {
    for (const file of fileList) {
      if (!file?.originFileObj) {
        message.error(t('datasets.pleaseUpload'));
        return null;
      }
    }
    return fileList;
  };

  const buildFormDataForFile = (file: UploadFile): FormData => {
    const params = new FormData();
    params.append('dataset', formData?.dataset_id || '');
    params.append('name', file.name);
    params.append('train_data', file.originFileObj!);
    Object.entries(selectTags).forEach(([key, val]) => {
      params.append(key, String(val));
    });
    return params;
  };

  const buildFormDataForImages = (files: UploadFile[], name: string): FormData => {
    const params = new FormData();
    params.append('dataset', formData?.dataset_id || '');
    params.append('name', name);
    Object.entries(selectTags).forEach(([key, val]) => {
      params.append(key, String(val));
    });
    files.forEach((file) => {
      if (file.originFileObj) {
        params.append('images', file.originFileObj);
      }
    });
    return params;
  };

  // 处理提交成功
  const handleSubmitSuccess = () => {
    setVisiable(false);
    setFileList([]);
    message.success(t('datasets.uploadSuccess'));
    onSuccess();
    resetFormState();
  };

  // 处理提交错误
  const handleSubmitError = (error: any) => {
    console.log(error);
    message.error(t('datasets.uploadError') || '上传失败，请重试');
  };

  const handleSubmit = async () => {
    setConfirmLoading(true);

    try {
      const validatedFiles = validateFileUpload();
      if (!validatedFiles?.length) return;

      if (!SUPPORTED_UPLOAD_TYPES.includes(activeType as any)) {
        throw new Error(`Unsupported type: ${activeType}`);
      }

      const uploadApi = UPLOAD_API[activeType];
      if (!uploadApi) {
        throw new Error(`API not found for type: ${activeType}`);
      }

      let uploadData: FormData;

      if (IMAGE_TYPES.includes(activeType)) {
        const { name } = await formRef.current?.validateFields();
        uploadData = buildFormDataForImages(validatedFiles, name);
      } else {
        uploadData = buildFormDataForFile(validatedFiles[0]);
      }

      await uploadApi(uploadData);

      handleSubmitSuccess();

    } catch (error) {
      handleSubmitError(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  // 重置表单状态
  const resetFormState = () => {
    setFileList([]);
    setCheckedType([]);
    setSelectTags({});
    setConfirmLoading(false);
    formRef.current?.resetFields();
  };

  const handleCancel = () => {
    setVisiable(false);
    resetFormState();
  };

  const downloadTemplate = async () => {
    const data = [
      {
        "value": 27.43789942218143,
        "timestamp": 1704038400
      },
      {
        "value": 26.033612999373652,
        "timestamp": 1704038460
      },
      {
        "value": 36.30777324191053,
        "timestamp": 1704038520
      },
      {
        "value": 33.70226097527219,
        "timestamp": 1704038580
      }
    ];
    const columns = ['timestamp', 'value']
    const blob = exportToCSV(data, columns);
    if (blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'template.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else {
      message.error(t('datasets.downloadError'));
    }
  };

  const CheckedType = () => (
    <div className='text-left flex justify-between items-center'>
      <div className='flex-1'>
        <span className='leading-8 mr-2'>{t(`mlops-common.type`) + ": "} </span>
        <Checkbox.Group onChange={onSelectChange} value={checkedType}>
          <Checkbox value={'is_train_data'}>{t(`datasets.train`)}</Checkbox>
          <Checkbox value={'is_val_data'}>{t(`datasets.validate`)}</Checkbox>
          <Checkbox value={'is_test_data'}>{t(`datasets.test`)}</Checkbox>
        </Checkbox.Group>
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
      {config?.fileType === 'image' &&
        <Form layout='vertical' ref={formRef}>
          <Form.Item
            name="name"
            label={t(`common.name`)}
            rules={[{ required: true, message: t(`common.inputMsg`) }]}
          >
            <Input />
          </Form.Item>
        </Form>
      }
      <Dragger {...props}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{t('datasets.uploadText')}</p>
      </Dragger>
      {config?.fileType !== 'image' && (
        <p>{t(`datasets.downloadCSV`)}<Button type='link' onClick={downloadTemplate}>{t('datasets.template')}</Button></p>
      )}
    </OperateModal>
  )
});

UploadModal.displayName = 'UploadModal';
export default UploadModal;