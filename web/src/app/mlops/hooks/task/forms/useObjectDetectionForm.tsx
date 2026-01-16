import { useState, useCallback, useEffect, RefObject } from 'react';
import { FormInstance, message, Form, Select, Input, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';
import type { Option } from '@/types';
import type { TrainJob } from '@/app/mlops/types/task';
import { OBJECT_DETECTION_ALGORITHM_CONFIGS, OBJECT_DETECTION_ALGORITHM_SCENARIOS } from '@/app/mlops/constants';

interface ModalState {
  isOpen: boolean;
  type: string;
  title: string;
}

interface UseObjectDetectionFormProps {
  datasetOptions: Option[];
  activeTag: string[];
  onSuccess: () => void;
  formRef: RefObject<FormInstance>
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useObjectDetectionForm = ({ datasetOptions, onSuccess, formRef }: UseObjectDetectionFormProps) => {
  const { t } = useTranslation();
  const {
    addObjectDetectionTrainTask,
    updateObjectDetectionTrainTask,
    getDatasetReleases,
    getDatasetReleaseByID
  } = useMlopsTaskApi();

  const [modalState, setModalState] = useState<ModalState>({
    isOpen: false,
    type: 'add',
    title: 'addtask',
  });
  const [formData, setFormData] = useState<TrainJob | null>(null);
  const [loadingState, setLoadingState] = useState<{
    confirm: boolean;
    dataset: boolean;
    select: boolean;
  }>({
    confirm: false,
    dataset: false,
    select: false,
  });
  const [datasetVersions, setDatasetVersions] = useState<Option[]>([]);
  const [isShow, setIsShow] = useState<boolean>(false);

  // 当 formData 和 modalState.isOpen 改变时初始化表单
  useEffect(() => {
    if (formData && modalState.isOpen) {
      initializeForm(formData);
    }
  }, [modalState.isOpen, formData]);

  // 后端数据 → 表单数据
  const apiToForm = (data: any) => {
    const result: any = {
      name: data.name,
      algorithm: data.algorithm,
      dataset: data.dataset,
      dataset_version: data.dataset_version,
      max_evals: data.max_evals,
    };

    // 如果有 hyperopt_config，展开其中的参数
    if (data.hyperopt_config && data.hyperopt_config.hyperparams) {
      const hyperparams = data.hyperopt_config.hyperparams;
      if (hyperparams.model_name) {
        result.model_name = hyperparams.model_name;
      }
    }

    return result;
  };

  // 表单数据 → 后端数据
  const formToApi = (formValues: any) => {
    const hyperopt_config: Record<string, any> = {
      hyperparams: {
        model_name: formValues.model_name || 'yolo11n.pt'
      }
    };

    const result = {
      name: formValues.name,
      algorithm: formValues.algorithm,
      dataset: formValues.dataset,
      dataset_version: formValues.dataset_version,
      max_evals: formValues.max_evals,
      status: 'pending',
      description: formValues.name || '',
      hyperopt_config
    };
    return result;
  };

  // 显示模态框
  const showModal = useCallback(({ type, title, form }: { type: string; title: string; form: any }) => {
    setLoadingState((prev) => ({ ...prev, select: false }));
    setFormData(form);
    setModalState({
      isOpen: true,
      type,
      title: title as string,
    });
  }, []);

  // 初始化表单
  const initializeForm = async (formData: TrainJob) => {
    if (!formRef.current) return;
    formRef.current.resetFields();

    if (modalState.type === 'add') {
      formRef.current.setFieldsValue({
        max_evals: 50,
        model_name: 'yolo11n.pt'
      });
    } else if (formData) {
      const formValues = apiToForm(formData);
      formRef.current.setFieldsValue(formValues);
      setIsShow(true);
      handleAsyncDataLoading(formData.dataset_version as number);
    }
  };

  // 以数据集版本文件ID获取数据集ID
  const handleAsyncDataLoading = useCallback(async (dataset_version_id: number) => {
    if (!dataset_version_id) return;
    setLoadingState((prev) => ({ ...prev, select: true }));
    try {
      const { dataset } = await getDatasetReleaseByID('object_detection', dataset_version_id);
      if (dataset && formRef.current) {
        formRef.current.setFieldsValue({
          dataset
        });
        await renderOptions(dataset);
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [getDatasetReleaseByID]);

  // 渲染数据集版本选项
  const renderOptions = useCallback(async (dataset: number) => {
    setLoadingState(prev => ({ ...prev, select: true }));
    try {
      if (!formRef.current || !dataset) return;
      // 加载数据集版本
      const datasetVersions = await getDatasetReleases('object_detection', { dataset });
      const _versionOptions = datasetVersions.map((item: any) => ({
        label: item?.name || '',
        value: item?.id
      }));
      setDatasetVersions(_versionOptions);
      if (formData?.dataset_version) {
        formRef.current.setFieldsValue({
          dataset_version: formData.dataset_version
        });
      }
    } catch (e) {
      console.log(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [formData, getDatasetReleases]);

  // 算法变化处理
  const onAlgorithmChange = useCallback((algorithm: string) => {
    if (!formRef.current) return;

    const algorithmConfig = OBJECT_DETECTION_ALGORITHM_CONFIGS[algorithm];
    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      return;
    }

    // 设置默认值
    const defaultValues = {
      max_evals: 50,
      model_name: 'yolo11n.pt'
    };

    formRef.current.setFieldsValue(defaultValues);
    setIsShow(true);
  }, []);

  // 表单值变化处理（预留给将来扩展）
  const onFormValuesChange = useCallback((changedValues: any, allValues: any) => {
    // 预留给将来的依赖字段处理
    console.log(changedValues, allValues)
  }, []);

  // 提交处理
  const handleSubmit = useCallback(async () => {
    if (loadingState.confirm) return;
    setLoadingState((prev) => ({ ...prev, confirm: true }));

    try {
      const formValues = await formRef.current?.validateFields();
      const params = formToApi(formValues);

      if (modalState.type === 'add') {
        await addObjectDetectionTrainTask(params as any);
      } else {
        await updateObjectDetectionTrainTask(formData?.id as string, params as any);
      }

      setModalState((prev) => ({ ...prev, isOpen: false }));
      message.success(t(`common.${modalState.type}Success`));
      setIsShow(false);
      onSuccess();
    } catch (e) {
      console.log(e);
      message.error(t(`common.error`));
    } finally {
      setLoadingState((prev) => ({ ...prev, confirm: false }));
    }
  }, [modalState.type, formData, onSuccess, addObjectDetectionTrainTask, updateObjectDetectionTrainTask, formToApi, t, loadingState.confirm]);

  // 取消处理
  const handleCancel = useCallback(() => {
    setModalState({
      isOpen: false,
      type: 'add',
      title: 'addtask',
    });
    formRef.current?.resetFields();
    setDatasetVersions([]);
    setFormData(null);
    setIsShow(false);
  }, []);

  // 渲染表单内容
  const renderFormContent = useCallback(() => {
    const currentAlgorithm = formRef.current?.getFieldValue('algorithm');

    return (
      <>
        {/* ========== 基础信息 - 始终显示 ========== */}
        <Form.Item name='name' label={t('common.name')} rules={[{ required: true, message: t('common.inputMsg') }]}>
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>

        <Form.Item name='algorithm' label={t('traintask.algorithms')} rules={[{ required: true, message: t('common.inputMsg') }]}>
          <Select
            placeholder={t('traintask.selectAlgorithmsMsg')}
            onChange={onAlgorithmChange}
            options={[
              { value: 'YOLO11Detection', label: 'YOLO11Detection' },
            ]}
          />
        </Form.Item>

        {currentAlgorithm && OBJECT_DETECTION_ALGORITHM_SCENARIOS[currentAlgorithm] && (
          <div style={{ marginTop: -16, marginBottom: 24, fontSize: 12, color: '#999' }}>
            {OBJECT_DETECTION_ALGORITHM_SCENARIOS[currentAlgorithm]}
          </div>
        )}

        <Form.Item name='dataset' label={t('traintask.datasets')} rules={[{ required: true, message: t('traintask.selectDatasets') }]}>
          <Select
            placeholder={t('traintask.selectDatasets')}
            loading={loadingState.select}
            options={datasetOptions}
            onChange={renderOptions}
          />
        </Form.Item>

        <Form.Item name='dataset_version' label="数据集版本" rules={[{ required: true, message: '请选择数据集版本' }]}>
          <Select
            placeholder="选择一个数据集版本"
            showSearch
            optionFilterProp="label"
            loading={loadingState.select}
            options={datasetVersions}
          />
        </Form.Item>

        <Form.Item name='max_evals' label="训练轮次" rules={[{ required: true, message: '请输入训练轮次' }]}>
          <InputNumber style={{ width: '100%' }} min={1} placeholder="训练的轮次" />
        </Form.Item>

        {/* ========== 算法配置（简化版） ========== */}
        {isShow && (
          <Form.Item name='model_name' label="预训练模型" rules={[{ required: true, message: '请选择预训练模型' }]}>
            <Select
              placeholder="选择预训练模型"
              options={[
                { label: 'YOLOv11n (最快)', value: 'yolo11n.pt' },
                { label: 'YOLOv11s (轻量级)', value: 'yolo11s.pt' },
                { label: 'YOLOv11m (平衡型，推荐)', value: 'yolo11m.pt' },
                { label: 'YOLOv11l (高精度)', value: 'yolo11l.pt' },
                { label: 'YOLOv11x (最高精度)', value: 'yolo11x.pt' }
              ]}
            />
          </Form.Item>
        )}
      </>
    );
  }, [t, datasetOptions, datasetVersions, loadingState.select, isShow, onAlgorithmChange, renderOptions]);

  return {
    modalState,
    formRef,
    loadingState,
    showModal,
    handleSubmit,
    handleCancel,
    renderFormContent,
    onFormValuesChange,
  };
};
