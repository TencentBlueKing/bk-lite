"use client";
import OperateModal from '@/components/operate-modal';
import { useState, useImperativeHandle, forwardRef, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { exportToCSV } from '@/app/mlops/utils/common';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Upload, Button, message, Checkbox, type UploadFile, type UploadProps, Input, Form, FormInstance } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { ModalConfig, ModalRef, TableData, DatasetType } from '@/app/mlops/types';
import { useSearchParams } from 'next/navigation';
import JSZip from 'jszip';
const { Dragger } = Upload;

interface UploadModalProps {
  onSuccess: () => void
}

const SUPPORTED_UPLOAD_TYPES = [
  DatasetType.ANOMALY_DETECTION,
  DatasetType.TIMESERIES_PREDICT,
  DatasetType.CLASSIFICATION,
  DatasetType.IMAGE_CLASSIFICATION,
  DatasetType.OBJECT_DETECTION,
  DatasetType.LOG_CLUSTERING
] as const;

const IMAGE_TYPES = [DatasetType.IMAGE_CLASSIFICATION, DatasetType.OBJECT_DETECTION];

const UploadModal = forwardRef<ModalRef, UploadModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const activeType = searchParams.get('activeTap') || '';
  const {
    addAnomalyTrainData,
    addTimeSeriesPredictTrainData,
    addImageClassificationTrainData,
    addObjectDetectionTrainData,
    addLogClusteringTrainData,
    addClassificationTrainData
  } = useMlopsManageApi();

  const UPLOAD_API: Record<string, (data: FormData) => Promise<any>> = {
    [DatasetType.ANOMALY_DETECTION]: addAnomalyTrainData,
    [DatasetType.TIMESERIES_PREDICT]: addTimeSeriesPredictTrainData,
    [DatasetType.IMAGE_CLASSIFICATION]: addImageClassificationTrainData,
    [DatasetType.OBJECT_DETECTION]: addObjectDetectionTrainData,
    [DatasetType.LOG_CLUSTERING]: addLogClusteringTrainData,
    [DatasetType.CLASSIFICATION]: addClassificationTrainData
  };

  const FILE_CONFIG: Record<string, { accept: string; maxCount: number; fileType: string }> = {
    [DatasetType.ANOMALY_DETECTION]: { accept: '.csv', maxCount: 1, fileType: 'csv' },
    [DatasetType.TIMESERIES_PREDICT]: { accept: '.csv', maxCount: 1, fileType: 'csv' },
    [DatasetType.IMAGE_CLASSIFICATION]: { accept: 'image/*', maxCount: 10, fileType: 'image' },
    [DatasetType.OBJECT_DETECTION]: { accept: 'image/*', maxCount: 10, fileType: 'image' },
    [DatasetType.LOG_CLUSTERING]: { accept: '.txt', maxCount: 1, fileType: 'txt' },
    [DatasetType.CLASSIFICATION]: { accept: '.csv', maxCount: 1, fileType: 'csv' },
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

  // 验证图片文件名格式（只允许英文、数字、下划线，长度1-64）
  const validateImageFileName = (fileName: string): {
    valid: boolean;
    reason?: string
  } => {
    if (!fileName || fileName.trim() === '') {
      return { valid: false, reason: t('datasets.fileNameEmpty') };
    }

    // 取最后一个点分割文件名和扩展名
    const lastDotIndex = fileName.lastIndexOf('.');

    if (lastDotIndex === -1) {
      return {
        valid: false,
        reason: t('datasets.fileNameMustHaveExtension')
      };
    }

    if (lastDotIndex === 0) {
      return {
        valid: false,
        reason: t('datasets.fileNameEmpty')
      };
    }

    const mainName = fileName.substring(0, lastDotIndex);

    // 长度限制：1-64个字符
    if (mainName.length < 1) {
      return {
        valid: false,
        reason: t('datasets.fileNameEmpty')
      };
    }

    if (mainName.length > 64) {
      return {
        valid: false,
        reason: t('datasets.fileNameTooLong')
      };
    }

    // 只允许英文字母、数字、下划线
    const validNamePattern = /^[a-zA-Z0-9_]+$/;
    if (!validNamePattern.test(mainName)) {
      return {
        valid: false,
        reason: t('datasets.fileNameInvalidChars')
      };
    }

    return { valid: true };
  };

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
    customRequest: ({ onSuccess }) => {
      // 阻止自动上传，只做文件收集
      // 实际上传会在用户点击"确认"按钮时在 handleSubmit 中进行
      setTimeout(() => {
        onSuccess?.("ok");
      }, 0);
    },
    beforeUpload: async (file) => {
      if (!config) return Upload.LIST_IGNORE;

      if (config.fileType === 'csv') {
        const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
        if (!isCSV) {
          message.warning(t('datasets.uploadWarn'));
          return Upload.LIST_IGNORE;
        }
        return true;
      } else if (config.fileType === 'txt') {
        const isTXT = file.type === "text/plain" || file.name.endsWith('.txt');
        if (!isTXT) {
          message.warning(t('datasets.uploadTxtWarn'));
          return Upload.LIST_IGNORE;
        }
        return true;
      } else if (config.fileType === 'image') {
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

  const buildFormDataForImages = async (files: UploadFile[], name: string): Promise<FormData> => {
    // 创建ZIP实例
    const zip = new JSZip();

    // 将所有图片添加到ZIP（扁平化结构）
    files.forEach((file) => {
      if (file.originFileObj) {
        zip.file(file.name, file.originFileObj);
      }
    });

    // 生成ZIP Blob
    const zipBlob = await zip.generateAsync({
      type: 'blob',
      compression: 'DEFLATE',
      compressionOptions: {
        level: 6  // 压缩级别 1-9
      }
    });

    // 构建FormData
    const params = new FormData();
    params.append('dataset', formData?.dataset_id || '');
    params.append('name', name);
    params.append('train_data', zipBlob, `${name}.zip`);  // 使用train_data字段
    Object.entries(selectTags).forEach(([key, val]) => {
      params.append(key, String(val));
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
    message.error(t('datasets.uploadError'));
  };

  const handleSubmit = async () => {
    const validatedFiles = validateFileUpload();
    if (!validatedFiles?.length) return;

    setConfirmLoading(true);

    try {
      // 图片文件名格式验证
      if (IMAGE_TYPES.includes(activeType as DatasetType)) {
        const invalidFiles: string[] = [];

        validatedFiles.forEach(file => {
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
                  {t(`datasets.fileNameVaild`)}
                </div>
                {invalidFiles.map((msg, idx) => (
                  <div key={idx} style={{ fontSize: 12, marginLeft: 8, marginTop: 4 }}>
                    • {msg}
                  </div>
                ))}
              </div>
            ),
            duration: 6
          });
          setConfirmLoading(false);
          return;
        }
      }

      if (!SUPPORTED_UPLOAD_TYPES.includes(activeType as any)) {
        throw new Error(`Unsupported type: ${activeType}`);
      }

      const uploadApi = UPLOAD_API[activeType];
      if (!uploadApi) {
        throw new Error(`API not found for type: ${activeType}`);
      }

      let uploadData: FormData;

      if (IMAGE_TYPES.includes(activeType as DatasetType)) {
        const { name } = await formRef.current?.validateFields();
        uploadData = await buildFormDataForImages(validatedFiles, name);
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
      message.error(t('datasets.uploadError'));
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
        {config?.fileType === 'image' && (
          <p className="ant-upload-hint" style={{ fontSize: 12, color: '#999', margin: '4px 0 0' }}>
            {t(`datasets.fileNameVaild`)}
          </p>
        )}
      </Dragger>
      {config?.fileType !== 'image' && (
        <p>{t(`datasets.downloadCSV`)}<Button type='link' onClick={downloadTemplate}>{t('datasets.template')}</Button></p>
      )}
    </OperateModal>
  )
});

UploadModal.displayName = 'UploadModal';
export default UploadModal;