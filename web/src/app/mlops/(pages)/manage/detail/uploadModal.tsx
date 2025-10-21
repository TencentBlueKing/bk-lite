"use client";
import OperateModal from '@/components/operate-modal';
import { useState, useImperativeHandle, forwardRef } from 'react';
import { useTranslation } from '@/utils/i18n';
import { exportToCSV } from '@/app/mlops/utils/common';
import useMlopsManageApi from '@/app/mlops/api/manage';
import { Upload, Button, message, Checkbox, type UploadFile, type UploadProps } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { ModalConfig, ModalRef, TableData } from '@/app/mlops/types';
import { TrainDataParams } from '@/app/mlops/types/manage';
import { useSearchParams } from 'next/navigation';
const { Dragger } = Upload;

interface UploadModalProps {
  onSuccess: () => void
}

const UploadModal = forwardRef<ModalRef, UploadModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const activeType = searchParams.get('activeTap') || '';
  const { addAnomalyTrainData, addTimeSeriesPredictTrainData, addLogClusteringTrainData, addClassificationTrainData } = useMlopsManageApi();
  const [visiable, setVisiable] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
  const [fileList, setFileList] = useState<UploadFile<any>[]>([]);
  const [checkedType, setCheckedType] = useState<string[]>([]);
  const [selectTags, setSelectTags] = useState<{
    [key: string]: boolean
  }>({});
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
      if (activeType !== 'log_clustering') {
        const isCSV = file.type === "text/csv" || file.name.endsWith('.csv');
        if (!isCSV) {
          message.warning(t('datasets.uploadWarn'))
        }
        return isCSV;
      } else {
        const isTxt = file.type === 'text/plain' || file.name.endsWith('.txt');
        if (!isTxt) {
          message.warning(t('datasets.uploadWarn'))
        }
        return isTxt;
      }

    },
    accept: activeType !== 'log_clustering' ? '.csv' : '.txt'
  };

  const handleFileRead = (text: string, type: string): FileReadResult => {
    try {
      // 统一换行符为 \n
      const lines = text.replace(/\r\n|\r|\n/g, '\n')?.split('\n').filter(line => line.trim() !== '');

      if (!lines.length) return { train_data: [] };

      if (type !== 'log_clustering') {
        const headers = type === 'anomaly' ? ['timestamp', 'value', 'label'] : lines[0]?.split(',');

        if (!headers || headers.length === 0) {
          throw new Error('文件格式不正确');
        }

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

            if(type === 'anomaly') {
              obj['index'] = index;
            }
            return obj;
          }, {});
        });
        if (type === 'classification') {
          return {
            train_data: data as TrainDataParams[],
            headers
          };
        }
        return {
          train_data: data as TrainDataParams[]
        };
      }

      return {
        train_data: lines
      };
    } catch (error) {
      console.log(error);
      throw error;
    }
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

  // 定义数据类型
  type ProcessedData = TrainDataParams[] | string[] | {
    train_data: TrainDataParams[],
    headers: string[]
  };

  interface FileReadResult {
    train_data: TrainDataParams[] | string[];
    headers?: string[];
  }

  // 定义提交策略映射
  const submitStrategies = {
    anomaly: {
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
  const validateFileUpload = (): UploadFile<any> | null => {
    const file = fileList[0];
    if (!file?.originFileObj) {
      message.error(t('datasets.pleaseUpload'));
      return null;
    }
    return file;
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
      const file = validateFileUpload();
      if (!file) return;

      // 2. 获取当前类型的策略
      const strategy = submitStrategies[formData?.activeTap as keyof typeof submitStrategies];
      if (!strategy) {
        throw new Error(`Unsupported upload type: ${formData?.activeTap}`);
      }

      // 3. 读取并处理文件内容
      const text = await file.originFileObj!.text();
      const rawData = handleFileRead(text, formData?.activeTap || '');

      // 根据类型决定传递的数据结构
      let dataToProcess: ProcessedData;
      if (formData?.activeTap === 'classification' && rawData.headers) {
        dataToProcess = { headers: rawData.headers, train_data: rawData.train_data as TrainDataParams[] };
      } else {
        dataToProcess = rawData.train_data;
      }

      const processedData = strategy.processData(dataToProcess);

      // 4. 构建提交参数
      const params = buildSubmitParams(file, processedData);

      // 5. 调用对应的API
      await strategy.apiCall(params);

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
      <Dragger {...props}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{t('datasets.uploadText')}</p>
      </Dragger>
      <p>{t(`datasets.${activeType !== 'log_clustering' ? 'downloadCSV' : 'downloadTxt'}`)}<Button type='link' onClick={downloadTemplate}>{t('datasets.template')}</Button></p>
    </OperateModal>
  )
});

UploadModal.displayName = 'UploadModal';
export default UploadModal;