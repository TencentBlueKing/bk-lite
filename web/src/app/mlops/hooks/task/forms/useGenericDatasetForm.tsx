import { useState, useCallback, useEffect, RefObject } from 'react';
import { FormInstance, message, Form, Select, Input, InputNumber, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { Option } from '@/types';
import type { 
  TrainJob, 
  FieldConfig, 
  // AlgorithmConfig,
  TrainJobFormValues,
  CreateTrainJobParams,
  UpdateTrainJobParams,
  HyperoptConfig,
  DatasetType,
  DatasetRelease
} from '@/app/mlops/types';
import { AlgorithmFieldRenderer } from '@/app/mlops/components/AlgorithmFieldRenderer';
import {
  transformGroupData,
  reverseTransformGroupData,
  extractDefaultValues
} from '@/app/mlops/utils/algorithmConfigUtils';
import { useAlgorithmConfigs } from '@/app/mlops/hooks/useAlgorithmConfigs';
import type { AlgorithmType } from '@/app/mlops/types/algorithmConfig';

interface ModalState {
  isOpen: boolean;
  type: 'add' | 'edit';
  title: string;
}

interface ShowModalParams {
  type: 'add' | 'edit';
  title: string;
  form: TrainJob | null;
}

interface UseGenericDatasetFormProps {
  datasetType: DatasetType;
  datasetOptions: Option[];
  formRef: RefObject<FormInstance>;
  onSuccess: () => void;
  apiMethods: {
    addTask: (params: CreateTrainJobParams) => Promise<TrainJob>;
    updateTask: (id: string, params: UpdateTrainJobParams) => Promise<TrainJob>;
    getDatasetReleases: (
      datasetType: DatasetType, 
      params: { dataset: number }
    ) => Promise<DatasetRelease[]>;
    getDatasetReleaseByID: (
      datasetType: DatasetType, 
      id: number
    ) => Promise<DatasetRelease>;
  };
}

export const useGenericDatasetForm = ({
  datasetType,
  datasetOptions,
  formRef,
  onSuccess,
  apiMethods
}: UseGenericDatasetFormProps) => {
  const { t } = useTranslation();

  // 动态获取算法配置
  const {
    algorithmConfigs,
    algorithmScenarios,
    algorithmOptions,
    loading: configLoading,
    isUsingFallback
  } = useAlgorithmConfigs(datasetType as AlgorithmType);

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
  const [formValues, setFormValues] = useState<TrainJobFormValues>({
    name: '',
    algorithm: '',
    dataset: 0,
    dataset_version: 0,
    max_evals: 50
  });

  // 当 formData 和 modalState.isOpen 改变时初始化表单
  useEffect(() => {
    if (formData && modalState.isOpen) {
      initializeForm(formData);
    }
  }, [modalState.isOpen, formData]);

  // 后端数据 → 表单数据
  const apiToForm = useCallback((data: TrainJob): TrainJobFormValues => {
    const config = (data.hyperopt_config as HyperoptConfig) || {};
    const algorithm = data.algorithm;
    const algorithmConfig = algorithm ? algorithmConfigs[algorithm] : null;

    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      return {
        name: '',
        algorithm: '',
        dataset: 0,
        dataset_version: 0,
        max_evals: 50
      };
    }

    const result: TrainJobFormValues = {
      name: data.name,
      algorithm: data.algorithm || '',
      dataset: Number(data.dataset) || 0,
      dataset_version: Number(data.dataset_version) || 0,
      max_evals: data.max_evals || 50,
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
  }, [algorithmConfigs]);

  // 表单数据 → 后端数据
  const formToApi = useCallback((formValues: TrainJobFormValues): CreateTrainJobParams => {
    const algorithm = formValues.algorithm;
    const algorithmConfig = algorithmConfigs[algorithm];

    if (!algorithmConfig) {
      console.error(`Unknown algorithm: ${algorithm}`);
      // 返回最小有效参数
      return {
        name: formValues.name,
        algorithm: formValues.algorithm,
        dataset: formValues.dataset,
        dataset_version: formValues.dataset_version,
        max_evals: formValues.max_evals,
        status: 'pending',
        description: formValues.name || '',
        hyperopt_config: {}
      };
    }

    const hyperopt_config: HyperoptConfig = {};

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

    const result: CreateTrainJobParams = {
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
  }, [algorithmConfigs]);

  // 显示模态框
  const showModal = useCallback(({ type, title, form }: ShowModalParams) => {
    setLoadingState((prev) => ({ ...prev, select: false }));
    setFormData(form);
    setModalState({
      isOpen: true,
      type,
      title,
    });
  }, []);

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
      const { dataset } = await apiMethods.getDatasetReleaseByID(datasetType, dataset_version_id);
      if (dataset && formRef.current) {
        formRef.current.setFieldsValue({
          dataset
        });
        await renderOptions(dataset);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [datasetType, apiMethods.getDatasetReleaseByID]);

  // 渲染数据集版本选项
  const renderOptions = useCallback(async (dataset: number) => {
    setLoadingState(prev => ({ ...prev, select: true }));
    try {
      if (!formRef.current || !dataset) return;
      // 加载数据集版本
      const datasetVersions = await apiMethods.getDatasetReleases(datasetType, { dataset });
      const _versionOptions: Option[] = datasetVersions.map((item: DatasetRelease) => ({
        label: item?.name || '',
        value: String(item?.id)
      }));
      setDatasetVersions(_versionOptions);
      if (formData?.dataset_version) {
        formRef.current.setFieldsValue({
          dataset_version: formData.dataset_version
        });
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingState(prev => ({ ...prev, select: false }));
    }
  }, [formData, datasetType, apiMethods.getDatasetReleases]);

  // 算法变化处理
  const onAlgorithmChange = useCallback((algorithm: string) => {
    if (!formRef.current) return;

    const algorithmConfig = algorithmConfigs[algorithm];
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
  }, [algorithmConfigs]);

  // 表单值变化处理（用于更新 formValues 状态）
  const onFormValuesChange = useCallback((changedValues: Partial<TrainJobFormValues>, allValues: TrainJobFormValues) => {
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
        await apiMethods.addTask(params);
      } else {
        await apiMethods.updateTask(formData?.id as string, params);
      }

      setModalState((prev) => ({ ...prev, isOpen: false }));
      message.success(t(`common.${modalState.type}Success`));
      setIsShow(false);
      onSuccess();
    } catch (e) {
      console.error(e);
      message.error(t(`common.error`));
    } finally {
      setLoadingState((prev) => ({ ...prev, confirm: false }));
    }
  }, [modalState.type, formData, onSuccess, apiMethods, formToApi, t, loadingState.confirm]);

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
    setFormValues({
      name: '',
      algorithm: '',
      dataset: 0,
      dataset_version: 0,
      max_evals: 50
    });
    setIsShow(false);
  }, []);

  // 渲染表单内容
  const renderFormContent = useCallback(() => {
    // 配置加载中
    if (configLoading) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip={t('common.loading')} />
        </div>
      );
    }

    const currentAlgorithm = formRef.current?.getFieldValue('algorithm');
    const algorithmConfig = currentAlgorithm ? algorithmConfigs[currentAlgorithm] : null;

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
            options={algorithmOptions}
          />
        </Form.Item>

        {currentAlgorithm && algorithmScenarios[currentAlgorithm] && (
          <div style={{ marginTop: -16, marginBottom: 24, fontSize: 12, color: '#999' }}>
            {algorithmScenarios[currentAlgorithm]}
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

        <Form.Item 
          name='max_evals' 
          label="训练轮次" 
          rules={[{ required: true, message: '请输入训练轮次' }]}
          tooltip="超参数优化的最大迭代次数。值越大搜索空间越充分，但训练时间越长。推荐范围: 50-200"
        >
          <InputNumber style={{ width: '100%' }} min={1} max={1000} placeholder="超参数搜索的评估轮次" />
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
  }, [t, configLoading, datasetOptions, datasetVersions, loadingState.select, isShow, formValues, algorithmConfigs, algorithmScenarios, algorithmOptions, onAlgorithmChange, renderOptions]);

  return {
    modalState,
    formRef,
    loadingState,
    configLoading,
    isUsingFallback,
    showModal,
    handleSubmit,
    handleCancel,
    renderFormContent,
    onFormValuesChange,
  };
};
