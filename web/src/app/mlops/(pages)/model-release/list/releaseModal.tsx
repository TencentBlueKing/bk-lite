'use client';
import { ModalRef, Option, DatasetType } from "@/app/mlops/types";
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
    addImageClassificationServings, updateImageClassificationServings,
    addObjectDetectionServings, updateObjectDetectionServings,
    getModelVersionList
  } = useMlopsModelReleaseApi();
  const formRef = useRef<FormInstance>(null);
  const [type, setType] = useState<string>('add');
  const [formData, setFormData] = useState<any>(null);
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [versionOptions, setVersionOptions] = useState<Option[]>([]);
  const [versionLoading, setVersionLoading] = useState<boolean>(false);
  const [confirmLoading, setConfirmLoading] = useState<boolean>(false);

  const [tagName] = activeTag;

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

    if (type === 'add') {
      const defaultValues: Record<string, any> = {
        model_version: 'latest',
        status: true
      };

      formRef.current.setFieldsValue(defaultValues);
    } else {
      const editValues: Record<string, any> = {
        ...formData,
        status: formData.status === 'active' ? true : false,
        port: formData.port || undefined // port 为 null 时设置为 undefined，让表单为空
      };
      getModelVersionListWithTrainJob(formData.train_job, tagName as DatasetType);
      formRef.current.setFieldsValue(editValues);
    }
  };

  const handleAddMap: Record<string, ((params: any) => Promise<void>) | null> = {
    [DatasetType.ANOMALY_DETECTION]: async (params: any) => {
      await addAnomalyServings(params);
    },
    [DatasetType.RASA]: null, // RASA 类型留空
    [DatasetType.LOG_CLUSTERING]: async (params: any) => {
      await addLogClusteringServings(params);
    },
    [DatasetType.TIMESERIES_PREDICT]: async (params: any) => {
      await addTimeseriesPredictServings(params);
    },
    [DatasetType.CLASSIFICATION]: async (params: any) => {
      await addClassificationServings(params);
    },
    [DatasetType.IMAGE_CLASSIFICATION]: async (params: any) => {
      await addImageClassificationServings(params);
    },
    [DatasetType.OBJECT_DETECTION]: async (params: any) => {
      await addObjectDetectionServings(params);
    },
  };

  const handleUpdateMap: Record<string, ((id: number, params: any) => Promise<void>) | null> = {
    [DatasetType.ANOMALY_DETECTION]: async (id: number, params: any) => {
      await updateAnomalyServings(id, params);
    },
    [DatasetType.RASA]: null, // RASA 类型留空
    [DatasetType.LOG_CLUSTERING]: async (id: number, params: any) => {
      await updateLogClusteringServings(id, params);
    },
    [DatasetType.TIMESERIES_PREDICT]: async (id: number, params: any) => {
      await updateTimeSeriesPredictServings(id, params);
    },
    [DatasetType.CLASSIFICATION]: async (id: number, params: any) => {
      await updateClassificationServings(id, params);
    },
    [DatasetType.IMAGE_CLASSIFICATION]: async (id: number, params: any) => {
      await updateImageClassificationServings(id, params);
    },
    [DatasetType.OBJECT_DETECTION]: async (id: number, params: any) => {
      await updateObjectDetectionServings(id, params);
    },
  };

  // 获取训练任务对应的模型列表
  const getModelVersionListWithTrainJob = async (id: number, key: DatasetType) => {
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
      console.error(e);
    } finally {
      setVersionLoading(false);
    }
  };

  const onTrainJobChange = (value: number, key: string) => {
    getModelVersionListWithTrainJob(value, key as DatasetType);
  };

  const handleConfirm = async () => {
    setConfirmLoading(true);
    try {
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
      console.error(e);
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
            rules={[{ required: true, message: t(`common.inputMsg`) }]}
          >
            <Input placeholder={t(`common.inputMsg`)} />
          </Form.Item>

          <Form.Item
            name='train_job'
            label={t(`traintask.traintask`)}
            rules={[{ required: true, message: t(`common.inputMsg`) }]}
          >
            <Select options={trainjobs} placeholder={t(`model-release.selectTraintask`)} onChange={(value) => onTrainJobChange(value, tagName)} />
          </Form.Item>

          <Form.Item
            name='model_version'
            label={t(`model-release.modelVersion`)}
            rules={[{ required: true, message: t(`common.inputMsg`) }]}
          >
            <Select placeholder={t(`mlops-common.inputVersionMsg`)} loading={versionLoading} options={versionOptions} />
          </Form.Item>

          <Form.Item
            name='port'
            label={t(`mlops-common.port`)}
          >
            <InputNumber className="w-full" placeholder={t(`mlops-common.portIptMsg`)} min={1} max={65535} />
          </Form.Item>

          <Form.Item
            name='description'
            label={t(`model-release.modelDescription`)}
            rules={[{ required: true, message: t(`common.inputMsg`) }]}
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