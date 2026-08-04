'use client';
import {
  forwardRef,
  useImperativeHandle,
  useState,
  useCallback,
  useEffect,
} from 'react';
import {
  Form,
  Input,
  Switch,
  message,
  Tabs,
  Alert,
  Button,
} from 'antd';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useAlgorithmConfigApi from '@/app/mlops/api/algorithmConfig';
import JsonEditor from './JsonEditor';
import FormPreview from './FormPreview';
import type {
  AlgorithmConfigEntity,
  AlgorithmConfigListItem,
  AlgorithmConfigParams,
  AlgorithmType,
  FormConfig,
} from '@/app/mlops/types/algorithmConfig';

interface AlgorithmConfigModalProps {
  algorithmType: AlgorithmType;
  onSuccess: () => void;
}

interface ModalState {
  isOpen: boolean;
  type: 'add' | 'edit';
  title: string;
}

interface ShowModalParams {
  type: string;
  title: string;
  form: AlgorithmConfigListItem | null;
}

// 内置默认模板只在新建时本地化；保存后的 form_config 按原始内容渲染。
const createDefaultFormConfig = (t: (key: string) => string): FormConfig => ({
  groups: {
    hyperparams: [
      {
        title: t('algorithmConfig.defaultForm.basicConfig'),
        fields: [
          {
            name: ['hyperparams', 'metric'],
            label: t('algorithmConfig.defaultForm.optimizationMetric'),
            type: 'select',
            required: true,
            placeholder: t('algorithmConfig.defaultForm.selectOptimizationMetric'),
            tooltip: t('algorithmConfig.defaultForm.optimizationMetricTooltip'),
            defaultValue: 'f1',
            options: [
              { label: t('algorithmConfig.defaultForm.f1Score'), value: 'f1' },
              { label: t('algorithmConfig.defaultForm.precision'), value: 'precision' },
              { label: t('algorithmConfig.defaultForm.recall'), value: 'recall' },
              { label: t('algorithmConfig.defaultForm.aucRoc'), value: 'auc' },
            ],
          },
          {
            name: ['hyperparams', 'random_state'],
            label: t('algorithmConfig.defaultForm.randomSeed'),
            type: 'inputNumber',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.randomSeedTooltip'),
            placeholder: t('algorithmConfig.defaultForm.randomSeedPlaceholder'),
            defaultValue: 42,
            min: 0,
            max: 2147483647,
            step: 1,
          },
        ],
      },
      {
        title: t('algorithmConfig.defaultForm.searchSpace'),
        fields: [
          {
            name: ['hyperparams', 'search_space', 'contamination'],
            label: t('algorithmConfig.defaultForm.contamination'),
            type: 'stringArray',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.contaminationTooltip'),
            placeholder: t('algorithmConfig.defaultForm.contaminationPlaceholder'),
            defaultValue: '0.01,0.05,0.1',
          },
        ],
      },
      {
        title: '',
        subtitle: t('algorithmConfig.defaultForm.advancedOptions'),
        fields: [
          {
            name: ['hyperparams', 'use_feature_engineering'],
            label: t('algorithmConfig.defaultForm.enableFeatureEngineering'),
            type: 'switch',
            defaultValue: false,
            layout: 'horizontal',
            tooltip: t('algorithmConfig.defaultForm.featureEngineeringTooltip'),
          },
        ],
      },
    ],
    preprocessing: [
      {
        title: t('algorithmConfig.defaultForm.preprocessing'),
        fields: [
          {
            name: ['preprocessing', 'handle_missing'],
            label: t('algorithmConfig.defaultForm.missingValueHandling'),
            type: 'select',
            required: true,
            placeholder: t('algorithmConfig.defaultForm.selectMissingValueHandling'),
            defaultValue: 'interpolate',
            options: [
              { label: t('algorithmConfig.defaultForm.interpolate'), value: 'interpolate' },
              { label: t('algorithmConfig.defaultForm.forwardFill'), value: 'ffill' },
              { label: t('algorithmConfig.defaultForm.backwardFill'), value: 'bfill' },
              { label: t('algorithmConfig.defaultForm.drop'), value: 'drop' },
              { label: t('algorithmConfig.defaultForm.median'), value: 'median' },
            ],
          },
          {
            name: ['preprocessing', 'max_missing_ratio'],
            label: t('algorithmConfig.defaultForm.maxMissingRatio'),
            type: 'inputNumber',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.maxMissingRatioTooltip'),
            placeholder: '0.0 - 1.0',
            defaultValue: 0.3,
            min: 0,
            max: 1,
            step: 0.1,
          },
          {
            name: ['preprocessing', 'label_column'],
            label: t('algorithmConfig.defaultForm.labelColumn'),
            type: 'input',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.labelColumnTooltip'),
            placeholder: t('algorithmConfig.defaultForm.labelColumnPlaceholder'),
            defaultValue: 'label',
          },
        ],
      },
    ],
    feature_engineering: [
      {
        title: t('algorithmConfig.defaultForm.featureEngineering'),
        fields: [
          {
            name: ['feature_engineering', 'lag_periods'],
            label: t('algorithmConfig.defaultForm.lagPeriods'),
            type: 'stringArray',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.lagPeriodsTooltip'),
            placeholder: t('algorithmConfig.defaultForm.lagPeriodsPlaceholder'),
            defaultValue: '1,2,3',
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'rolling_windows'],
            label: t('algorithmConfig.defaultForm.rollingWindowSize'),
            type: 'stringArray',
            required: true,
            tooltip: t('algorithmConfig.defaultForm.rollingWindowSizeTooltip'),
            placeholder: t('algorithmConfig.defaultForm.rollingWindowSizePlaceholder'),
            defaultValue: '12,24,48',
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'rolling_features'],
            label: t('algorithmConfig.defaultForm.rollingWindowStatistics'),
            type: 'multiSelect',
            required: true,
            placeholder: t('algorithmConfig.defaultForm.selectStatisticsFunction'),
            defaultValue: ['mean', 'std', 'min', 'max'],
            options: [
              { label: t('algorithmConfig.defaultForm.mean'), value: 'mean' },
              { label: t('algorithmConfig.defaultForm.standardDeviation'), value: 'std' },
              { label: t('algorithmConfig.defaultForm.minimum'), value: 'min' },
              { label: t('algorithmConfig.defaultForm.maximum'), value: 'max' },
            ],
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'use_temporal_features'],
            label: t('algorithmConfig.defaultForm.temporalFeatures'),
            type: 'switch',
            defaultValue: true,
            layout: 'horizontal',
            tooltip: t('algorithmConfig.defaultForm.temporalFeaturesTooltip'),
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
        ],
      },
    ],
  },
});

const AlgorithmConfigModal = forwardRef<{ showModal: (params: ShowModalParams) => void }, AlgorithmConfigModalProps>(({ algorithmType, onSuccess }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const {
    getAlgorithmConfigById,
    createAlgorithmConfig,
    updateAlgorithmConfig,
  } = useAlgorithmConfigApi();

  const [modalState, setModalState] = useState<ModalState>({
    isOpen: false,
    type: 'add',
    title: 'addConfig',
  });
  const [formData, setFormData] = useState<AlgorithmConfigListItem | null>(null);
  const [formConfig, setFormConfig] = useState<FormConfig>(() => createDefaultFormConfig(t));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('basic');

  useImperativeHandle(ref, () => ({
    showModal: ({ type, title, form: formRecord }: ShowModalParams) => {
      setFormData(formRecord);
      setModalState({
        isOpen: true,
        type: type as 'add' | 'edit',
        title,
      });
      setActiveTab('basic');
      setJsonError(null);
    },
  }));

  // 加载详情（编辑时获取完整 form_config）
  useEffect(() => {
    if (modalState.isOpen && formData && modalState.type === 'edit') {
      loadConfigDetail(formData.id);
    } else if (modalState.isOpen && modalState.type === 'add') {
      form.resetFields();
      form.setFieldsValue({
        algorithm_type: algorithmType,
        is_active: true,
      });
      setFormConfig(createDefaultFormConfig(t));
    }
  }, [modalState.isOpen, formData, modalState.type, algorithmType, t]);

  const loadConfigDetail = async (id: number) => {
    setLoading(true);
    try {
      const data: AlgorithmConfigEntity = await getAlgorithmConfigById(algorithmType, id);
      form.setFieldsValue({
        name: data.name,
        display_name: data.display_name,
        scenario_description: data.scenario_description,
        image: data.image,
        is_active: data.is_active,
      });
      setFormConfig(data.form_config);
    } catch (e) {
      console.error(e);
      message.error(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleFormConfigChange = useCallback((value: string) => {
    try {
      const parsed = JSON.parse(value);
      setFormConfig(parsed);
      setJsonError(null);
    } catch (e) {
      setJsonError((e as Error).message);
    }
  }, []);

  const handleSubmit = async () => {
    if (jsonError) {
      message.error(t('algorithmConfig.jsonError'));
      return;
    }

    try {
      const values = await form.validateFields();
      setLoading(true);

      const params: AlgorithmConfigParams = {
        algorithm_type: algorithmType,
        name: values.name,
        display_name: values.display_name,
        scenario_description: values.scenario_description,
        image: values.image,
        form_config: formConfig,
        is_active: values.is_active ?? true,
      };

      if (modalState.type === 'add') {
        await createAlgorithmConfig(algorithmType, params);
        message.success(t('common.addSuccess'));
      } else {
        await updateAlgorithmConfig(algorithmType, formData!.id, params);
        message.success(t('common.updateSuccess'));
      }

      setModalState((prev) => ({ ...prev, isOpen: false }));
      onSuccess();
    } catch (e) {
      console.error(e);
      message.error(t('common.error'));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setModalState({
      isOpen: false,
      type: 'add',
      title: 'addConfig',
    });
    setFormData(null);
    setFormConfig(createDefaultFormConfig(t));
    setJsonError(null);
    form.resetFields();
  };

  const tabItems = [
    {
      key: 'basic',
      label: t('algorithmConfig.basicInfo'),
      children: (
        <Form
          form={form}
          layout="vertical"
        >
          <Form.Item
            name="name"
            label={t('algorithmConfig.algorithmName')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
            tooltip={t('algorithmConfig.algorithmNameTooltip')}
          >
            <Input
              placeholder={t('algorithmConfig.algorithmNamePlaceholder')}
              disabled={modalState.type === 'edit'}
            />
          </Form.Item>

          <Form.Item
            name="display_name"
            label={t('algorithmConfig.displayName')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={t('algorithmConfig.displayNamePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="scenario_description"
            label={t('algorithmConfig.scenarioDescription')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('algorithmConfig.scenarioDescriptionPlaceholder')}
            />
          </Form.Item>

          <Form.Item
            name="image"
            label={t('algorithmConfig.image')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
            tooltip={t('algorithmConfig.imageTooltip')}
          >
            <Input placeholder={t('algorithmConfig.imagePlaceholder')} />
          </Form.Item>

          <Form.Item
            name="is_active"
            label={t('algorithmConfig.isActive')}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'formConfig',
      label: t('algorithmConfig.formConfig'),
      children: (
        <div>
          {jsonError && (
            <Alert
              message={t('algorithmConfig.jsonError')}
              description={jsonError}
              type="error"
              className="mb-2"
              showIcon
            />
          )}
          <JsonEditor
            value={JSON.stringify(formConfig, null, 2)}
            onChange={handleFormConfigChange}
            height="40vh"
          />
        </div>
      ),
    },
    {
      key: 'preview',
      label: t('algorithmConfig.preview'),
      children: (
        <FormPreview formConfig={formConfig} />
      ),
    },
  ];

  return (
    <OperateModal
      title={t(`algorithmConfig.${modalState.title}`)}
      open={modalState.isOpen}
      onCancel={handleCancel}
      footer={[
        <Button key="submit" loading={loading} type="primary" onClick={handleSubmit}>
          {t('common.confirm')}
        </Button>,
        <Button key="cancel" onClick={handleCancel}>
          {t('common.cancel')}
        </Button>,
      ]}
      width={700}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </OperateModal>
  );
});

AlgorithmConfigModal.displayName = 'AlgorithmConfigModal';

export default AlgorithmConfigModal;
