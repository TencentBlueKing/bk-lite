import { useState, useCallback, useEffect, RefObject } from 'react';
import { Form, Input, Select, InputNumber, Switch, message, Divider, Row, Col } from 'antd';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';
import type { Option } from '@/types';
import type { TrainJob } from '@/app/mlops/types/task';

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
  const [useFeatureEngineering, setUseFeatureEngineering] = useState<boolean>(true);
  const [useDiffFeatures, setUseDiffFeatures] = useState<boolean>(true);

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
    const config = data.hyperopt_config || {};
    const hyperparams = config.hyperparams || {};
    const searchSpace = hyperparams.search_space || {};
    const featureEngineering = config.feature_engineering || {};

    // 辅助函数：数组转逗号分隔字符串
    const arrayToString = (arr: any[]) => arr ? arr.join(',') : '';

    return {
      name: data.name,
      algorithm: data.algorithm,
      dataset: data.dataset,
      dataset_version: data.dataset_version,

      // 展开 hyperparams
      max_evals: data.max_evals,  // 直接读取顶层字段（由后端保证一致性）
      metric: hyperparams.metric,
      use_feature_engineering: hyperparams.use_feature_engineering ?? true,
      random_state: hyperparams.random_state,
      search_space: {
        n_estimators: arrayToString(searchSpace.n_estimators),
        learning_rate: arrayToString(searchSpace.learning_rate),
        max_depth: arrayToString(searchSpace.max_depth),
        min_samples_split: arrayToString(searchSpace.min_samples_split),
        min_samples_leaf: arrayToString(searchSpace.min_samples_leaf),
        subsample: arrayToString(searchSpace.subsample),
        lag_features: arrayToString(searchSpace.lag_features)
      },

      // 展开 feature_engineering
      feature_engineering: {
        lag_periods: arrayToString(featureEngineering.lag_periods),
        rolling_windows: arrayToString(featureEngineering.rolling_windows),
        rolling_features: featureEngineering.rolling_features,
        use_temporal_features: featureEngineering.use_temporal_features,
        use_cyclical_features: featureEngineering.use_cyclical_features,
        use_diff_features: featureEngineering.use_diff_features,
        diff_periods: arrayToString(featureEngineering.diff_periods)
      },

      // 展开 preprocessing
      preprocessing: config.preprocessing
    };
  };

  // 表单数据 → 后端数据
  const formToApi = (formValues: any) => {
    // 辅助函数：逗号分隔字符串转数组（自动转换数字）
    const stringToArray = (str: string) => {
      if (!str) return [];
      return str.split(',').map(item => {
        const trimmed = item.trim();
        const num = Number(trimmed);
        return isNaN(num) ? trimmed : num;
      });
    };

    const searchSpace = formValues.search_space || {};
    const featureEngineering = formValues.feature_engineering || {};

    const hyperopt_config: Record<string, any> = {
      // hyperparams 部分
      hyperparams: {
        use_feature_engineering: formValues.use_feature_engineering ?? true,
        random_state: formValues.random_state ?? 42,
        metric: formValues.metric,
        search_space: {
          n_estimators: stringToArray(searchSpace.n_estimators),
          learning_rate: stringToArray(searchSpace.learning_rate),
          max_depth: stringToArray(searchSpace.max_depth),
          min_samples_split: stringToArray(searchSpace.min_samples_split),
          min_samples_leaf: stringToArray(searchSpace.min_samples_leaf),
          subsample: stringToArray(searchSpace.subsample),
          lag_features: stringToArray(searchSpace.lag_features)
        }
      },

      // preprocessing 部分
      preprocessing: formValues.preprocessing
    };

    // feature_engineering 部分（如果启用）
    if (formValues.use_feature_engineering) {
      hyperopt_config.feature_engineering = {
        lag_periods: stringToArray(featureEngineering.lag_periods),
        rolling_windows: stringToArray(featureEngineering.rolling_windows),
        rolling_features: featureEngineering.rolling_features,
        use_temporal_features: featureEngineering.use_temporal_features,
        use_cyclical_features: featureEngineering.use_cyclical_features,
        use_diff_features: featureEngineering.use_diff_features,
        diff_periods: stringToArray(featureEngineering.diff_periods)
      };
    }

    return {
      name: formValues.name,
      algorithm: formValues.algorithm,
      dataset: formValues.dataset,
      dataset_version: formValues.dataset_version,
      max_evals: formValues.max_evals,  // 顶层字段，由后端同步到配置
      status: 'pending',
      description: formValues.name || '',
      hyperopt_config
    };
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
      setIsShow(true);
      setUseFeatureEngineering(formValues.use_feature_engineering ?? true);
      setUseDiffFeatures(formValues.feature_engineering?.use_diff_features ?? true);
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
  const onAlgorithmChange = useCallback(() => {
    if (!formRef.current) return;

    // 设置默认值
    const defaultValues = {
      max_evals: 50,
      metric: 'rmse',
      use_feature_engineering: true,
      random_state: 42,
      search_space: {
        n_estimators: '50,100,200,300',
        learning_rate: '0.01,0.05,0.1,0.2',
        max_depth: '3,5,7,10',
        min_samples_split: '2,5,10',
        min_samples_leaf: '1,2,4',
        subsample: '0.7,0.8,0.9,1.0',
        lag_features: '6,12,24'
      },
      feature_engineering: {
        lag_periods: '1,2,3,7,14',
        rolling_windows: '7,14,30',
        rolling_features: ['mean', 'std', 'min', 'max'],
        use_temporal_features: true,
        use_cyclical_features: false,
        use_diff_features: true,
        diff_periods: '1'
      },
      preprocessing: {
        handle_missing: 'interpolate',
        max_missing_ratio: 0.3,
        interpolation_limit: 3
      }
    };

    formRef.current.setFieldsValue(defaultValues);
    setIsShow(true);
    setUseFeatureEngineering(true);
    setUseDiffFeatures(true);
  }, []);

  // 特征工程开关变化处理
  const onFeatureEngineeringChange = useCallback((checked: boolean) => {
    setUseFeatureEngineering(checked);
  }, []);

  // 差分特征开关变化处理
  const onDiffFeaturesChange = useCallback((checked: boolean) => {
    setUseDiffFeatures(checked);
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
    setFormData(null);  // 清理表单数据状态
    setIsShow(false);
    setUseFeatureEngineering(true);
    setUseDiffFeatures(true);
  }, []);

  // 渲染表单内容
  const renderFormContent = useCallback(() => {
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
            options={[{ value: 'GradientBoosting', label: 'GradientBoosting' }]}
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

        {/* ========== 参数配置 - 第一层 if (isShow) ========== */}
        {isShow && (
          <>
            {/* 训练配置 */}
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              训练配置
            </Divider>

            <Form.Item name='metric' label="优化指标" rules={[{ required: true, message: t('common.inputMsg') }]}>
              <Select
                placeholder="选择优化目标指标"
                options={[
                  { label: 'RMSE (均方根误差)', value: 'rmse' },
                  { label: 'MAE (平均绝对误差)', value: 'mae' },
                  { label: 'MAPE (平均绝对百分比误差)', value: 'mape' }
                ]}
              />
            </Form.Item>

            <Form.Item 
              name='random_state' 
              label="随机种子" 
              tooltip="控制随机性，确保实验可复现。相同种子+相同参数=相同结果"
              rules={[{ required: true, message: '请输入随机种子' }]}
            >
              <InputNumber style={{ width: '100%' }} min={0} placeholder="例: 42" />
            </Form.Item>

            {/* 搜索空间 */}
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              搜索空间 (Search Space)
            </Divider>

            {/* 树结构参数 */}
            <div style={{ marginBottom: 12, color: '#666', fontSize: 13, fontWeight: 500 }}>
              树结构参数
            </div>

            <Form.Item name={['search_space', 'n_estimators']} label="树的数量" rules={[{ required: true, message: '请输入树的数量' }]}>
              <Input placeholder="例: 50,100,200,300" />
            </Form.Item>

            <Form.Item name={['search_space', 'max_depth']} label="树最大深度" rules={[{ required: true, message: '请输入树最大深度' }]}>
              <Input placeholder="例: 3,5,7,10" />
            </Form.Item>

            <Form.Item name={['search_space', 'learning_rate']} label="学习率" rules={[{ required: true, message: '请输入学习率' }]}>
              <Input placeholder="例: 0.01,0.05,0.1,0.2" />
            </Form.Item>

            {/* 采样控制参数 */}
            <div style={{ marginTop: 20, marginBottom: 12, color: '#666', fontSize: 13, fontWeight: 500 }}>
              采样控制参数
            </div>

            <Form.Item name={['search_space', 'min_samples_split']} label="最小分裂样本数" rules={[{ required: true, message: '请输入最小分裂样本数' }]}>
              <Input placeholder="例: 2,5,10" />
            </Form.Item>

            <Form.Item name={['search_space', 'min_samples_leaf']} label="叶节点最小样本数" rules={[{ required: true, message: '请输入叶节点最小样本数' }]}>
              <Input placeholder="例: 1,2,4" />
            </Form.Item>

            <Form.Item name={['search_space', 'subsample']} label="子采样比例" rules={[{ required: true, message: '请输入子采样比例' }]}>
              <Input placeholder="例: 0.7,0.8,0.9,1.0" />
            </Form.Item>

            {/* 特征参数 */}
            <div style={{ marginTop: 20, marginBottom: 12, color: '#666', fontSize: 13, fontWeight: 500 }}>
              特征参数
            </div>

            <Form.Item name={['search_space', 'lag_features']} label="滞后特征数量" rules={[{ required: true, message: '请输入滞后特征数量' }]}>
              <Input placeholder="例: 6,12,24" />
            </Form.Item>

            {/* Preprocessing */}
            {/* <Divider orientation="left">数据预处理 (Preprocessing)</Divider> */}
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              数据预处理 (Preprocessing)
            </Divider>

            <Form.Item name={['preprocessing', 'handle_missing']} label="缺失值处理" rules={[{ required: true, message: '请选择缺失值处理方式' }]}>
              <Select
                placeholder="选择缺失值处理方式"
                options={[
                  { label: '线性插值 (interpolate)', value: 'interpolate' },
                  { label: '前向填充 (ffill)', value: 'ffill' },
                  { label: '后向填充 (bfill)', value: 'bfill' },
                  { label: '删除 (drop)', value: 'drop' },
                  { label: '中位数填充 (median)', value: 'median' }
                ]}
              />
            </Form.Item>

            <Form.Item name={['preprocessing', 'max_missing_ratio']} label="最大缺失率" rules={[{ required: true, message: '请输入最大缺失率' }]}>
              <InputNumber
                style={{ width: '100%' }}
                min={0}
                max={1}
                step={0.1}
                placeholder="0.0 - 1.0"
              />
            </Form.Item>

            <Form.Item name={['preprocessing', 'interpolation_limit']} label="插值限制" rules={[{ required: true, message: '请输入插值限制' }]}>
              <InputNumber
                style={{ width: '100%' }}
                min={1}
                placeholder="最多填充的连续缺失点数"
              />
            </Form.Item>

            {/* 特征工程 */}
            <Divider orientation='start' orientationMargin={'0'} plain style={{ borderColor: '#d1d5db' }}>
              特征工程 (Feature Engineering)
            </Divider>

            <Form.Item name='use_feature_engineering' label="启用特征工程" valuePropName="checked" layout='horizontal'>
              <Switch defaultChecked size='small' onChange={onFeatureEngineeringChange}  />
            </Form.Item>

            {/* ========== Feature Engineering - 第二层 if (useFeatureEngineering) ========== */}
            {useFeatureEngineering && (
              <>
                <Form.Item name={['feature_engineering', 'lag_periods']} label="滞后期" rules={[{ required: true, message: '请输入滞后期' }]}>
                  <Input placeholder="例: 1,2,3,7,14" />
                </Form.Item>

                <Form.Item name={['feature_engineering', 'rolling_windows']} label="滚动窗口大小" rules={[{ required: true, message: '请输入滚动窗口大小' }]}>
                  <Input placeholder="例: 7,14,30" />
                </Form.Item>

                <Form.Item name={['feature_engineering', 'rolling_features']} label="滚动窗口统计" rules={[{ required: true, message: '请选择滚动窗口统计' }]}>
                  <Select
                    mode="multiple"
                    placeholder="选择统计函数"
                    maxTagCount={3}
                    options={[
                      { label: '均值 (mean)', value: 'mean' },
                      { label: '标准差 (std)', value: 'std' },
                      { label: '最小值 (min)', value: 'min' },
                      { label: '最大值 (max)', value: 'max' },
                      { label: '中位数 (median)', value: 'median' },
                      { label: '求和 (sum)', value: 'sum' }
                    ]}
                  />
                </Form.Item>

                <Row gutter={16} align='middle'>
                  <Col span={6}>
                    <Form.Item name={['feature_engineering', 'use_temporal_features']} label="时间特征" valuePropName="checked" layout='horizontal'>
                      <Switch defaultChecked size='small' />
                    </Form.Item>
                  </Col>
                  <Col span={6}>
                    <Form.Item name={['feature_engineering', 'use_cyclical_features']} label="周期性编码" valuePropName="checked" layout='horizontal'>
                      <Switch size='small' />
                    </Form.Item>
                  </Col>
                </Row>

                {/* 差分特征组 */}
                <Row gutter={16} align='middle'>
                  <Col span={6}>
                    <Form.Item name={['feature_engineering', 'use_diff_features']} label="差分特征" valuePropName="checked" layout='horizontal'>
                      <Switch defaultChecked size='small' onChange={onDiffFeaturesChange} />
                    </Form.Item>
                  </Col>
                  {useDiffFeatures && (
                    <Col span={18}>
                      <Form.Item name={['feature_engineering', 'diff_periods']} label="差分期数" layout='horizontal' rules={[{ required: true, message: '请输入差分期数' }]}>
                        <Input placeholder="例: 1" />
                      </Form.Item>
                    </Col>
                  )}
                </Row>
              </>
            )}
          </>
        )}
      </>
    );
  }, [t, datasetOptions, datasetVersions, loadingState.select, isShow, useFeatureEngineering, useDiffFeatures, onAlgorithmChange, onFeatureEngineeringChange, onDiffFeaturesChange, renderOptions]);

  return {
    modalState,
    formRef,
    loadingState,
    showModal,
    handleSubmit,
    handleCancel,
    renderFormContent,
  };
};
