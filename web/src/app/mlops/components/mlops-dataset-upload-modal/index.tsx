'use client';

import OperateFormModal from '@/components/operate-form-modal';
import UploadDropPanel from '@/components/upload-drop-panel';
import { useState, useImperativeHandle, forwardRef, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  message,
  Checkbox,
  Upload,
  type UploadFile,
  type UploadProps,
  Input,
  Form,
  FormInstance,
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import {
  DatasetType,
} from '@/app/mlops/components/mlops-shared';
import type {
  MlopsDatasetModalConfig,
  MlopsDatasetModalFormData,
  MlopsDatasetModalRef,
} from '@/app/mlops/components/mlops-dataset-shared/contracts';
import JSZip from 'jszip';

interface MlopsDatasetUploadModalProps {
  datasetType: DatasetType;
  onSuccess: () => void;
  uploadDataset: (datasetType: DatasetType, data: FormData) => Promise<void>;
}

const SUPPORTED_UPLOAD_TYPES = [
  DatasetType.ANOMALY_DETECTION,
  DatasetType.TIMESERIES_PREDICT,
  DatasetType.CLASSIFICATION,
  DatasetType.IMAGE_CLASSIFICATION,
  DatasetType.OBJECT_DETECTION,
  DatasetType.LOG_CLUSTERING,
] as const;

const IMAGE_TYPES = [
  DatasetType.IMAGE_CLASSIFICATION,
  DatasetType.OBJECT_DETECTION,
];

const UPLOAD_HINT_KEYS: Record<string, string> = {
  [DatasetType.ANOMALY_DETECTION]: 'datasets.uploadHintAnomaly',
  [DatasetType.TIMESERIES_PREDICT]: 'datasets.uploadHintTimeseries',
  [DatasetType.CLASSIFICATION]: 'datasets.uploadHintClassification',
  [DatasetType.IMAGE_CLASSIFICATION]: 'datasets.uploadHintImageClassification',
  [DatasetType.OBJECT_DETECTION]: 'datasets.uploadHintObjectDetection',
  [DatasetType.LOG_CLUSTERING]: 'datasets.uploadHintLogClustering',
};

const MlopsDatasetUploadModal = forwardRef<
  MlopsDatasetModalRef,
  MlopsDatasetUploadModalProps
>(({ datasetType, onSuccess, uploadDataset }, ref) => {
  const { t } = useTranslation();

  const FILE_CONFIG: Record<
    string,
    { accept: string; maxCount: number; fileType: string }
  > = {
    [DatasetType.ANOMALY_DETECTION]: {
      accept: '.csv',
      maxCount: 1,
      fileType: 'csv',
    },
    [DatasetType.TIMESERIES_PREDICT]: {
      accept: '.csv',
      maxCount: 1,
      fileType: 'csv',
    },
    [DatasetType.IMAGE_CLASSIFICATION]: {
      accept: 'image/*',
      maxCount: 10,
      fileType: 'image',
    },
    [DatasetType.OBJECT_DETECTION]: {
      accept: 'image/*',
      maxCount: 10,
      fileType: 'image',
    },
    [DatasetType.LOG_CLUSTERING]: {
      accept: '.txt',
      maxCount: 1,
      fileType: 'txt',
    },
    [DatasetType.CLASSIFICATION]: {
      accept: '.csv',
      maxCount: 1,
      fileType: 'csv',
    },
  };

  const [visible, setVisible] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [fileList, setFileList] = useState<UploadFile<any>[]>([]);
  const [checkedType, setCheckedType] = useState<string[]>([]);
  const [selectTags, setSelectTags] = useState<Record<string, boolean>>({});
  const [formData, setFormData] = useState<MlopsDatasetModalFormData>();
  const formRef = useRef<FormInstance>(null);

  useImperativeHandle(ref, () => ({
    showModal: ({ form }: MlopsDatasetModalConfig) => {
      setVisible(true);
      setFormData(form);
    },
  }));

  const validateImageFileName = (
    fileName: string,
  ): { valid: boolean; reason?: string } => {
    if (!fileName || fileName.trim() === '') {
      return { valid: false, reason: t('datasets.fileNameEmpty') };
    }

    const lastDotIndex = fileName.lastIndexOf('.');

    if (lastDotIndex === -1) {
      return {
        valid: false,
        reason: t('datasets.fileNameMustHaveExtension'),
      };
    }

    if (lastDotIndex === 0) {
      return {
        valid: false,
        reason: t('datasets.fileNameEmpty'),
      };
    }

    const mainName = fileName.substring(0, lastDotIndex);

    if (mainName.length < 1) {
      return {
        valid: false,
        reason: t('datasets.fileNameEmpty'),
      };
    }

    if (mainName.length > 64) {
      return {
        valid: false,
        reason: t('datasets.fileNameTooLong'),
      };
    }

    const validNamePattern = /^[a-zA-Z0-9_]+$/;
    if (!validNamePattern.test(mainName)) {
      return {
        valid: false,
        reason: t('datasets.fileNameInvalidChars'),
      };
    }

    return { valid: true };
  };

  const handleChange: UploadProps['onChange'] = ({ fileList }) => {
    setFileList(fileList);
  };

  const config = FILE_CONFIG[datasetType];
  const isImageType = IMAGE_TYPES.includes(datasetType as DatasetType);

  const props: UploadProps = {
    name: 'file',
    multiple: isImageType,
    directory: isImageType,
    maxCount: config?.maxCount || 1,
    fileList,
    onChange: handleChange,
    customRequest: ({ onSuccess }) => {
      setTimeout(() => {
        onSuccess?.('ok');
      }, 0);
    },
    beforeUpload: async (file) => {
      if (!config) return Upload.LIST_IGNORE;

      if (config.fileType === 'csv') {
        const isCSV = file.type === 'text/csv' || file.name.endsWith('.csv');
        if (!isCSV) {
          message.warning(t('datasets.uploadWarn'));
          return Upload.LIST_IGNORE;
        }
        return true;
      }

      if (config.fileType === 'txt') {
        const isTXT =
          file.type === 'text/plain' || file.name.endsWith('.txt');
        if (!isTXT) {
          message.warning(t('datasets.uploadTxtWarn'));
          return Upload.LIST_IGNORE;
        }
        return true;
      }

      if (config.fileType === 'image') {
        const isLt2M = file.size / 1024 / 1024 < 2;
        if (!isLt2M) {
          message.error(t('datasets.over2MB'));
          return Upload.LIST_IGNORE;
        }
        return true;
      }

      return true;
    },
    accept: config?.accept || '.csv',
  };

  const onSelectChange = (value: string[]) => {
    setCheckedType(value);
    const object = value.reduce((prev: Record<string, boolean>, current) => {
      return {
        ...prev,
        [current]: true,
      };
    }, {});
    setSelectTags(object);
  };

  const validateFileUpload = (): UploadFile[] | null => {
    if (!fileList.length) {
      message.error(t('datasets.pleaseUpload'));
      return null;
    }

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
    params.append('dataset', String(formData?.dataset_id || ''));
    params.append('name', file.name);
    params.append('train_data', file.originFileObj!);
    Object.entries(selectTags).forEach(([key, val]) => {
      params.append(key, String(val));
    });
    return params;
  };

  const buildFormDataForImages = async (
    files: UploadFile[],
    name: string,
  ): Promise<FormData> => {
    const zip = new JSZip();

    files.forEach((file) => {
      if (file.originFileObj) {
        zip.file(file.name, file.originFileObj);
      }
    });

    const zipBlob = await zip.generateAsync({
      type: 'blob',
      compression: 'DEFLATE',
      compressionOptions: {
        level: 6,
      },
    });

    const params = new FormData();
    params.append('dataset', String(formData?.dataset_id || ''));
    params.append('name', name);
    params.append('train_data', zipBlob, `${name}.zip`);
    Object.entries(selectTags).forEach(([key, val]) => {
      params.append(key, String(val));
    });

    return params;
  };

  const handleSubmitSuccess = () => {
    setVisible(false);
    setFileList([]);
    message.success(t('datasets.uploadSuccess'));
    onSuccess();
    resetFormState();
  };

  const handleSubmitError = (error: any) => {
    console.error(error);
    message.error(t('datasets.uploadError'));
  };

  const handleSubmit = async () => {
    const validatedFiles = validateFileUpload();
    if (!validatedFiles?.length) return;

    setConfirmLoading(true);

    try {
      if (IMAGE_TYPES.includes(datasetType as DatasetType)) {
        const invalidFiles: string[] = [];

        validatedFiles.forEach((file) => {
          const { valid, reason } = validateImageFileName(file.name);
          if (!valid && reason) {
            invalidFiles.push(`${file.name}: ${reason}`);
          }
        });

        if (invalidFiles.length > 0) {
          message.error({
            content: (
              <div>
                <div style={{ marginBottom: 8, fontWeight: 500 }}>
                  {t('datasets.fileNameVaild')}
                </div>
                {invalidFiles.map((msg, idx) => (
                  <div
                    key={idx}
                    style={{ fontSize: 12, marginLeft: 8, marginTop: 4 }}
                  >
                    • {msg}
                  </div>
                ))}
              </div>
            ),
            duration: 6,
          });
          setConfirmLoading(false);
          return;
        }
      }

      if (!SUPPORTED_UPLOAD_TYPES.includes(datasetType as any)) {
        throw new Error(`Unsupported type: ${datasetType}`);
      }

      let uploadData: FormData;

      if (IMAGE_TYPES.includes(datasetType as DatasetType)) {
        const { name } = await formRef.current?.validateFields();
        uploadData = await buildFormDataForImages(validatedFiles, name);
      } else {
        uploadData = buildFormDataForFile(validatedFiles[0]);
      }

      await uploadDataset(datasetType, uploadData);
      handleSubmitSuccess();
    } catch (error) {
      handleSubmitError(error);
    } finally {
      setConfirmLoading(false);
    }
  };

  const resetFormState = () => {
    setFileList([]);
    setCheckedType([]);
    setSelectTags({});
    setConfirmLoading(false);
    formRef.current?.resetFields();
  };

  const handleCancel = () => {
    setVisible(false);
    resetFormState();
  };

  const datasetTypeSelector = (
    <div className="text-left flex items-center">
      <div className="flex-1">
        <span className="leading-8 mr-2">{`${t('mlops-common.type')}: `}</span>
        <Checkbox.Group onChange={onSelectChange} value={checkedType}>
          <Checkbox value="is_train_data">{t('datasets.train')}</Checkbox>
          <Checkbox value="is_val_data">{t('datasets.validate')}</Checkbox>
          <Checkbox value="is_test_data">{t('datasets.test')}</Checkbox>
        </Checkbox.Group>
      </div>
    </div>
  );

  return (
    <OperateFormModal
      title={t('datasets.upload')}
      open={visible}
      onCancel={handleCancel}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      confirmLoading={confirmLoading}
      onConfirm={handleSubmit}
      extra={datasetTypeSelector}
    >
      {config?.fileType === 'image' ? (
        <Form layout="vertical" ref={formRef}>
          <Form.Item
            name="name"
            label={t('common.name')}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input />
          </Form.Item>
        </Form>
      ) : null}
      <UploadDropPanel
        name={props.name}
        fileList={props.fileList}
        onChange={props.onChange}
        customRequest={props.customRequest}
        beforeUpload={props.beforeUpload}
        onRemove={props.onRemove}
        accept={props.accept}
        maxCount={props.maxCount}
        multiple={props.multiple}
        directory={isImageType}
        showUploadList={props.showUploadList}
        icon={<InboxOutlined />}
        uploadText={
          isImageType ? t('datasets.uploadText') : t('datasets.uploadFileText')
        }
        uploadHint={
          <div style={{ fontSize: 12, color: '#999', margin: '4px 0 0' }}>
            <div>{t(UPLOAD_HINT_KEYS[datasetType])}</div>
            {isImageType ? <div>{t('datasets.fileNameVaild')}</div> : null}
          </div>
        }
      />
    </OperateFormModal>
  );
});

MlopsDatasetUploadModal.displayName = 'MlopsDatasetUploadModal';

export type { MlopsDatasetUploadModalProps };
export default MlopsDatasetUploadModal;
