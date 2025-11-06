"use client";
import OperateModal from '@/components/operate-modal';
import { useState, useImperativeHandle, forwardRef, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { handleFileRead, exportToCSV } from '@/app/mlops/utils/common';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Upload, Button, message, Checkbox, type UploadFile, type UploadProps, Input, Form, FormInstance } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { ModalConfig, ModalRef, TableData } from '@/app/mlops/types';
import { TrainDataParams } from '@/app/mlops/types/manage';
import { useSearchParams } from 'next/navigation';
import { TYPE_FILE_MAP } from '@/app/mlops/constants';
const { Dragger } = Upload;

interface UploadModalProps {
  onSuccess: () => void
}

// 定义数据类型
type ProcessedData = TrainDataParams[] | string[] | {
  train_data: TrainDataParams[],
  headers: string[]
};

const UploadModal = forwardRef<ModalRef, UploadModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const activeType = searchParams.get('activeTap') || '';
  const {
    addAnomalyTrainData,
    addTimeSeriesPredictTrainData,
    addLogClusteringTrainData,
    addClassificationTrainData,
    addImageClassificationTrainData,
    addObjectDetectionTrainData
  } = useMlopsManageApi();
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

  const props: UploadProps = {
    name: 'file',
    multiple: TYPE_FILE_MAP[activeType] !== 'image' ? false : true,
    maxCount: TYPE_FILE_MAP[activeType] !== 'image' ? 1 : 10,
    fileList: fileList,
    onChange: handleChange,
    beforeUpload: (file) => {
      if (TYPE_FILE_MAP[activeType] === 'csv') {
        const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
        if (!isCSV) {
          message.warning(t('datasets.uploadWarn'))
        }
        return isCSV;
      } else if (TYPE_FILE_MAP[activeType] === 'txt') {
        const isTxt = file.type === 'text/plain' || file.name.endsWith('.txt');
        if (!isTxt) {
          message.warning(t('datasets.uploadWarn'))
        }
        return isTxt;
      } else if (TYPE_FILE_MAP[activeType] === 'image') {
        // const isPng = file.type === 'image/png' || file.name.endsWith('.png');
        const isLt2M = file.size / 1024 / 1024 < 2;
        // if (!isPng) {
        //   message.error(t('datasets.uploadWarn'));
        // }
        if (!isLt2M) {
          message.error(t('datasets.over2MB'));
        }

        return (isLt2M) || Upload.LIST_IGNORE;
      }

    },
    accept: TYPE_FILE_MAP[activeType] !== 'image' ? `.${TYPE_FILE_MAP[activeType]}` : 'image/*',
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

  // 定义提交策略映射
  const submitStrategies = {
    anomaly_detection: {
      processData: (data: ProcessedData) => {
        const trainData = data as TrainDataParams[];
        return {
          train_data: trainData.map(item => ({ timestamp: item.timestamp, value: item.value })),
          metadata: {
            anomaly_point: trainData.filter(item => item?.label === 1).map(k => k.index)
          }
        };
      },
      apiCall: addAnomalyTrainData
    },
    timeseries_predict: {
      processData: (data: ProcessedData) => ({ train_data: data as TrainDataParams[] }),
      apiCall: addTimeSeriesPredictTrainData
    },
    log_clustering: {
      processData: (data: ProcessedData) => ({ train_data: data as string[] }),
      apiCall: addLogClusteringTrainData
    },
    classification: {
      processData: (data: ProcessedData) => {
        if (typeof data === 'object' && !Array.isArray(data) && 'train_data' in data) {
          return {
            train_data: data.train_data,
            metadata: {
              headers: data.headers
            }
          };
        }
        return {
          train_data: data
        };
      },
      apiCall: addClassificationTrainData
    }
  };

  // 验证文件上传
  const validateFileUpload = (): UploadFile<any>[] | null => {
    // const file = fileList[0];
    fileList.forEach((file) => {
      if (!file?.originFileObj) {
        message.error(t('datasets.pleaseUpload'));
        return null;
      }
    })

    return fileList;
  };

  // 构建通用参数
  const buildSubmitParams = (file: UploadFile<any>, processedData: any) => ({
    dataset: formData?.dataset_id,
    name: file.name,
    ...processedData,
    ...selectTags
  });

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
      // 1. 验证文件
      const fileList = validateFileUpload();
      if (!fileList?.length) return;

      if (TYPE_FILE_MAP[activeType] !== 'image') {
        // 2. 获取当前类型的策略
        const strategy = submitStrategies[formData?.activeTap as keyof typeof submitStrategies];
        if (!strategy) {
          throw new Error(`Unsupported upload type: ${formData?.activeTap}`);
        }
        // 3. 读取并处理文件内容
        const text = await fileList[0].originFileObj!.text();
        const incluede_header = formData?.activeTap === 'classification' ? true : false;
        const rawData = handleFileRead(text, formData?.activeTap || '', incluede_header);

        // 根据类型决定传递的数据结构
        let dataToProcess: ProcessedData;
        if (formData?.activeTap === 'classification' && rawData.headers) {
          dataToProcess = { headers: rawData.headers, train_data: rawData.train_data as TrainDataParams[] };
        } else {
          dataToProcess = rawData.train_data;
        }

        const processedData = strategy.processData(dataToProcess);

        // 4. 构建提交参数
        const params = buildSubmitParams(fileList[0], processedData);
        console.log(params);
        // 5. 调用对应的API
        await strategy.apiCall(params);
      } else {
        // 图片上传处理
        const value = await formRef.current?.validateFields();
        const submitData = new FormData();
        submitData.append('dataset', formData?.dataset_id || '');
        submitData.append('name', value.name);

        // 添加标签
        Object.entries(selectTags).forEach(([key, val]) => {
          submitData.append(key, String(val));
        });

        // 添加图片文件
        fileList.forEach((file) => {
          if (file.originFileObj) {
            submitData.append('images', file.originFileObj);
          }
        });

        // 根据类型调用不同的API
        if (formData?.activeTap === 'image_classification') {
          await addImageClassificationTrainData(submitData);
        } else if (formData?.activeTap === 'object_detection') {
          await addObjectDetectionTrainData(submitData);
        }
      }

      // 6. 处理成功
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
        <span className='leading-[32px] mr-2'>{t(`mlops-common.type`) + ": "} </span>
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
      {TYPE_FILE_MAP[activeType] === 'image' &&
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
      {TYPE_FILE_MAP[activeType] !== 'image' && (
        <p>{t(`datasets.${activeType !== 'log_clustering' ? 'downloadCSV' : 'downloadTxt'}`)}<Button type='link' onClick={downloadTemplate}>{t('datasets.template')}</Button></p>
      )}
    </OperateModal>
  )
});

UploadModal.displayName = 'UploadModal';
export default UploadModal;