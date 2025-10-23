'use client';
import { ModalRef, Option } from "@/app/mlops/types";
import { forwardRef, useImperativeHandle, useState, useRef, useEffect } from "react";
import OperateModal from '@/components/operate-modal';
import { Form, FormInstance, Select, Button, Input, InputNumber, message } from "antd";
import { useTranslation } from "@/utils/i18n";
import useMlopsModelReleaseApi from "@/app/mlops/api/modelRelease";
const { TextArea } = Input;

interface ReleaseModalProps {
  trainjobs: Option[],
  onSuccess: () => void;
  activeTag: string[];
}

const ReleaseModal = forwardRef<ModalRef, ReleaseModalProps>(({ trainjobs, activeTag, onSuccess }, ref) => {
  const { t } = useTranslation();
  const { 
    addAnomalyServings, updateAnomalyServings,
    addLogClusteringServings, updateLogClusteringServings,
    addTimeseriesPredictServings, updateTimeSeriesPredictServings,
    addClassificationServings, updateClassificationServings
  } = useMlopsModelReleaseApi();
  const formRef = useRef<FormInstance>(null);
  const [type, setType] = useState<string>('add');
  const [formData, setFormData] = useState<any>(null);
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);

  useImperativeHandle(ref, () => ({
    showModal: ({ type, form }) => {
      setType(type);
      setFormData(form);
      setModalOpen(true);
      setConfirmLoading(false);
    }
  }));

  useEffect(() => {
    if (modalOpen) {
      initializeForm();
    }
  }, [modalOpen])

  useEffect(() => {
    if (modalOpen) {
      initializeForm();
    }
  }, [activeTag])

  const initializeForm = () => {
    if (!formRef.current) return;
    formRef.current.resetFields();
    
    const [tagName] = activeTag;
    
    if (type === 'add') {
      const defaultValues: Record<string, any> = {
        model_version: 'latest',
        status: true
      };
      
      // 只有 anomaly 类型才设置默认阈值
      if (tagName === 'anomaly') {
        defaultValues.anomaly_threshold = 0.5;
      }
      
      formRef.current.setFieldsValue(defaultValues);
    } else {
      const editValues: Record<string, any> = {
        ...formData,
        status: formData.status === 'active' ? true : false
      };
      
      formRef.current.setFieldsValue(editValues);
    }
  };

  // 渲染不同类型的特有字段
  const renderTypeSpecificFields = () => {
    const [tagName] = activeTag;
    
    switch (tagName) {
      case 'anomaly':
        return (
          <>
            <Form.Item
              name='anomaly_detection_train_job'
              label={t(`traintask.traintask`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} />
            </Form.Item>
            <Form.Item
              name='anomaly_threshold'
              label={t(`model-release.modelThreshold`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <InputNumber className="w-full" placeholder={t(`model-release.inputThreshold`)} />
            </Form.Item>
          </>
        );
      
      case 'log_clustering':
        return (
          <>
            <Form.Item
              name='log_clustering_train_job'
              label={t(`traintask.traintask`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} />
            </Form.Item>
            <Form.Item
              name='api_endpoint'
              label={t(`model-release.apiEndpoint`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Input placeholder={t(`model-release.inputApiEndpoint`)} />
            </Form.Item>
            <Form.Item
              name='max_requests_per_minute'
              label={t(`model-release.maxRequestsPerMinute`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <InputNumber className="w-full" placeholder={t(`model-release.inputMaxRequests`)} />
            </Form.Item>
            <Form.Item
              name='supported_log_formats'
              label={t(`model-release.supportedLogFormats`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <TextArea placeholder={t(`model-release.inputLogFormats`)} rows={2} />
            </Form.Item>
          </>
        );
      
      case 'timeseries_predict':
        return (
          <Form.Item
            name='time_series_predict_train_job'
            label={t(`traintask.traintask`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} />
          </Form.Item>
        );

      case 'classification': 
        return (
          <Form.Item
            name='classification_train_job'
            label={t(`traintask.traintask`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} />
          </Form.Item>
        )
      
      default:
        return null;
    }
  };

  const handleAddMap: Record<string, ((params: any) => Promise<void>) | null> = {
    'anomaly': async (params: any) => {
      await addAnomalyServings(params);
    },
    'rasa': null, // RASA 类型留空
    'log_clustering': async (params: any) => {
      await addLogClusteringServings(params);
    },
    'timeseries_predict': async (params: any) => {
      await addTimeseriesPredictServings(params);
    },
    'classification': async (params: any) => {
      await addClassificationServings(params);
    },
  };

  const handleUpdateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    'anomaly': async (id: number, params: any) => {
      await updateAnomalyServings(id, params);
    },
    'rasa': null, // RASA 类型留空
    'log_clustering': async (id: number, params: any) => {
      await updateLogClusteringServings(id, params);
    },
    'timeseries_predict': async (id: number, params: any) => {
      await updateTimeSeriesPredictServings(id, params);
    },
    'classification': async (id: number, params: any) => {
      await updateClassificationServings(id, params);
    },
  };

  const handleConfirm = async () => {
    setConfirmLoading(true);
    try {
      const [tagName] = activeTag;
      const data = await formRef.current?.validateFields();

      if (type === 'add') {
        if (!handleAddMap[tagName]) {
          return;
        }
        await handleAddMap[tagName]!({ status: 'active', ...data });
        message.success(t(`model-release.publishSuccess`));
      } else {
        if (!handleUpdateMap[tagName]) {
          return;
        }
        await handleUpdateMap[tagName]!(formData?.id, data);
        message.success(t(`common.updateSuccess`));
      }
      setModalOpen(false);
      onSuccess();
    } catch (e) {
      console.log(e);
      message.error(t(`common.error`));
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    setModalOpen(false);
  };

  return (
    <>
      <OperateModal
        title={t(`model-release.modalTitle`)}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={[
          <Button key='submit' type="primary" onClick={handleConfirm} loading={confirmLoading}>{t(`common.confirm`)}</Button>,
          <Button key='cancel' onClick={handleCancel}>{t(`common.cancel`)}</Button>
        ]}
      >
        <Form ref={formRef} layout="vertical">
          {/* 公共字段 */}
          <Form.Item
            name='name'
            label={t(`model-release.modelName`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input placeholder={t(`common.inputMsg`)} />
          </Form.Item>
          
          {/* 不同类型的特有字段 */}
          {renderTypeSpecificFields()}
          
          <Form.Item
            name='model_version'
            label={t(`model-release.modelVersion`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input placeholder={t(`model-release.inputVersionMsg`)} />
          </Form.Item>
          
          <Form.Item
            name='description'
            label={t(`model-release.modelDescription`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <TextArea placeholder={t(`common.inputMsg`)} rows={4} />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  )
});

ReleaseModal.displayName = 'ReleaseModal';
export default ReleaseModal;