'use client';
import { ModalRef, Option, DatasetReleaseKey } from "@/app/mlops/types";
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
    addClassificationServings, updateClassificationServings,
    getModelVersionList
  } = useMlopsModelReleaseApi();
  const formRef = useRef<FormInstance>(null);
  const [type, setType] = useState<string>('add');
  const [formData, setFormData] = useState<any>(null);
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [versionOptions, setVersionOptions] = useState<Option[]>([]);
  const [versionLoading, setVersionLoading] = useState<boolean>(false);
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
      if (tagName === 'anomaly_detection') {
        defaultValues.anomaly_threshold = 0.5;
      }

      formRef.current.setFieldsValue(defaultValues);
    } else {
      const editValues: Record<string, any> = {
        ...formData,
        status: formData.status === 'active' ? true : false,
        port: formData.port || undefined // port 为 null 时设置为 undefined，让表单为空
      };
      getModelVersionListWithTrainJob(formData.id, tagName as DatasetReleaseKey);
      formRef.current.setFieldsValue(editValues);
    }
  };

  // 渲染不同类型的特有字段
  const renderTypeSpecificFields = () => {
    const [tagName] = activeTag;

    switch (tagName) {
      case 'anomaly_detection':
        return (
          <>
            <Form.Item
              name='anomaly_detection_train_job'
              label={t(`traintask.traintask`)}
              rules={[{ required: true, message: t('common.inputMsg') }]}
            >
              <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} onChange={(value) => onTrainJobChange(value, tagName)} />
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
              <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} onChange={(value) => onTrainJobChange(value, tagName)} />
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
            <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} onChange={(value) => onTrainJobChange(value, tagName)} />
          </Form.Item>
        );

      case 'classification':
        return (
          <Form.Item
            name='classification_train_job'
            label={t(`traintask.traintask`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} onChange={(value) => onTrainJobChange(value, tagName)} />
          </Form.Item>
        )

      default:
        return null;
    }
  };

  const handleAddMap: Record<string, ((params: any) => Promise<void>) | null> = {
    'anomaly_detection': async (params: any) => {
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
    'anomaly_detection': async (id: number, params: any) => {
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

  // 获取训练任务对应的模型列表
  const getModelVersionListWithTrainJob = async (id: number, key: DatasetReleaseKey) => {
    setVersionLoading(true);
    try {
      const data = await getModelVersionList(id, key);
      const ready_versions = data.versions?.filter((item: any) => item.status === 'READY') || [];
      const options = ready_versions.map((item: any) => ({
        label: `Version_${item?.version}`,
        value: item?.version
      }));
      options.unshift({ label: 'latest', value: 'latest' });

      setVersionOptions(options);
    } catch (e) {
      console.log(e);
    } finally {
      setVersionLoading(false);
    }
  };

  const onTrainJobChange = (value: number, key: string) => {
    getModelVersionListWithTrainJob(value, key as DatasetReleaseKey);
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
            <Select placeholder={t(`model-release.inputVersionMsg`)} loading={versionLoading} options={versionOptions} />
          </Form.Item>

          <Form.Item
            name='port'
            label={'端口'}
            extra={
              type === 'edit' && formData?.container_info?.port
                ? `当前运行端口：${formData.container_info.port}${formData.port ? ' (用户指定)' : ' (自动分配)'}`
                : '留空则由 Docker 自动分配端口'
            }
          >
            <InputNumber className="w-full" placeholder={'请输入端口号'} min={1} max={65535} />
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