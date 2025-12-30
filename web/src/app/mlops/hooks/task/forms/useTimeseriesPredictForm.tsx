import { useState, useCallback, useEffect, RefObject } from 'react';
import { Form, Input, Select, InputNumber, message } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';
import type { Option } from '@/types';
import type { TrainJob, FieldConfig } from '@/app/mlops/types/task';
import { TIMESERIES_ALGORITHM_CONFIGS } from '@/app/mlops/constants';
import { AlgorithmFieldRenderer } from '@/app/mlops/components/AlgorithmFieldRenderer';
import { 
  transformGroupData, 
  reverseTransformGroupData,
  extractDefaultValues 
} from '@/app/mlops/utils/algorithmConfigUtils';

interface ModalState {
  isOpen: boolean;
  type: string;
  title: string;
}

interface UseTimeseriesPredictFormProps {
  datasetOptions: Option[];
  activeTag: string[]; // 保留以保持接口一致性
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useTimeseriesPredictForm = ({
  datasetOptions,
  // activeTag,
  onSuccess,
  formRef
}: UseTimeseriesPredictFormProps) => {
  const { t } = useTranslation();
  const {
    addTimeSeriesTrainTask,
    updateTimeSeriesTrainTask,
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
  const [formValues, setFormValues] = useState<any>({}); // 用于 AlgorithmFieldRenderer 的依赖检查

  // 当 formData 和 modalState.isOpen 改变时初始化表单
  useEffect(() => {
    if (formData && modalState.isOpen) {
      initializeForm(formData);
    }
  }, [modalState.isOpen, formData]);

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

  // 后端数据 → 表单数据
  const apiToForm = (data: any) => {
    console.log('===== [apiToForm] 从后端读取的原始数据 =====');
    console.log('[apiToForm] data:', JSON.stringify(data, null, 2));
    console.log('[apiToForm] hyperopt_config:', JSON.stringify(data.hyperopt_config, null, 2));
    const config = data.hyperopt_config || {};
    const algorithm = data.algorithm;
    const algorithmConfig = TIMESERIES_ALGORITHM_CONFIGS[algorithm];

    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      return {};
    }

    const result: any = {
      name: data.name,
      algorithm: data.algorithm,
      dataset: data.dataset,
      dataset_version: data.dataset_version,
      max_evals: data.max_evals,
    };

    // 转换 hyperparams
    if (algorithmConfig.groups.hyperparams) {
      const allHyperparamFields = algorithmConfig.groups.hyperparams.flatMap(g => g.fields);
      const hyperparamsData = reverseTransformGroupData(config, allHyperparamFields);
      Object.assign(result, hyperparamsData);
    }

    // 转换 preprocessing
    if (algorithmConfig.groups.preprocessing && config.preprocessing) {
      const allPreprocessingFields = algorithmConfig.groups.preprocessing.flatMap(g => g.fields);
      const preprocessingData = reverseTransformGroupData(config, allPreprocessingFields);
      Object.assign(result, preprocessingData);
    }

    // 转换 feature_engineering
    if (algorithmConfig.groups.feature_engineering && config.feature_engineering) {
      const allFeatureEngineeringFields = algorithmConfig.groups.feature_engineering.flatMap(g => g.fields);
      const featureEngineeringData = reverseTransformGroupData(config, allFeatureEngineeringFields);
      Object.assign(result, featureEngineeringData);
    }

    return result;
  };

  // 表单数据 → 后端数据
  const formToApi = (formValues: any) => {
    const algorithm = formValues.algorithm;
    const algorithmConfig = TIMESERIES_ALGORITHM_CONFIGS[algorithm];

    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      return {};
    }

    const hyperopt_config: Record<string, any> = {};

    // 转换所有配置组
    const allFields: FieldConfig[] = [];
    if (algorithmConfig.groups.hyperparams) {
      allFields.push(...algorithmConfig.groups.hyperparams.flatMap(g => g.fields));
    }
    if (algorithmConfig.groups.preprocessing) {
      allFields.push(...algorithmConfig.groups.preprocessing.flatMap(g => g.fields));
    }
    if (algorithmConfig.groups.feature_engineering) {
      allFields.push(...algorithmConfig.groups.feature_engineering.flatMap(g => g.fields));
    }

    // 一次性转换所有字段，transformGroupData 会根据字段的 name 路径自动分组
    const transformed = transformGroupData(formValues, allFields);
    Object.assign(hyperopt_config, transformed);

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
    
    console.log('===== [formToApi] 提交给后端的数据 =====');
    console.log('[formToApi] result:', JSON.stringify(result, null, 2));
    console.log('[formToApi] hyperopt_config:', JSON.stringify(hyperopt_config, null, 2));
    return result;
  };

  // 初始化表单
  const initializeForm = async (formData: TrainJob) => {
    if (!formRef.current) return;
    formRef.current.resetFields();

    if (modalState.type === 'add') {
      formRef.current.setFieldsValue({
        max_evals: 50
      });
    } else if (formData) {
      const formValues = apiToForm(formData);
      formRef.current.setFieldsValue(formValues);
      setFormValues(formValues);
      setIsShow(true);
      handleAsyncDataLoading(formData.dataset_version as number);
    }
  };

  // 以数据集版本文件ID获取数据集ID
  const handleAsyncDataLoading = useCallback(async (dataset_version_id: number) => {
    if (!dataset_version_id) return;
    setLoadingState((prev) => ({ ...prev, select: true }));
    try {
      const { dataset } = await getDatasetReleaseByID(dataset_version_id);
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
      const datasetVersions = await getDatasetReleases({ dataset });
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

    const algorithmConfig = TIMESERIES_ALGORITHM_CONFIGS[algorithm];
    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      return;
    }

    // 从配置中提取默认值
    const defaultValues = {
      max_evals: 50,
      ...extractDefaultValues(algorithmConfig)
    };

    formRef.current.setFieldsValue(defaultValues);
    setFormValues(defaultValues);
    setIsShow(true);
  }, []);

  // 表单值变化处理（用于更新 formValues 状态）
  const onFormValuesChange = useCallback((changedValues: any, allValues: any) => {
    setFormValues(allValues);
  }, []);

  // 提交处理
  const handleSubmit = useCallback(async () => {
    if (loadingState.confirm) return;
    setLoadingState((prev) => ({ ...prev, confirm: true }));

    try {
      const formValues = await formRef.current?.validateFields();
      const params = formToApi(formValues);

      if (modalState.type === 'add') {
        await addTimeSeriesTrainTask(params as any);
      } else {
        await updateTimeSeriesTrainTask(formData?.id as string, params as any);
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
  }, [modalState.type, formData, onSuccess, addTimeSeriesTrainTask, updateTimeSeriesTrainTask, formToApi, t, loadingState.confirm]);

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
    setFormValues({});
    setIsShow(false);
  }, []);

  // 渲染表单内容
  const renderFormContent = useCallback(() => {
    const currentAlgorithm = formRef.current?.getFieldValue('algorithm');
    const algorithmConfig = currentAlgorithm ? TIMESERIES_ALGORITHM_CONFIGS[currentAlgorithm] : null;

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
              { value: 'GradientBoosting', label: 'GradientBoosting' },
              { value: 'RandomForest', label: 'RandomForest' }
            ]}
          />
        </Form.Item>

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
          <InputNumber style={{ width: '100%' }} min={1} placeholder="超参数搜索的评估轮次" />
        </Form.Item>

        {/* ========== 算法特定配置 ========== */}
        {isShow && algorithmConfig && (
          <AlgorithmFieldRenderer
            config={algorithmConfig}
            formValues={formValues}
          />
        )}
      </>
    );
  }, [t, datasetOptions, datasetVersions, loadingState.select, isShow, formValues, onAlgorithmChange, renderOptions]);

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
