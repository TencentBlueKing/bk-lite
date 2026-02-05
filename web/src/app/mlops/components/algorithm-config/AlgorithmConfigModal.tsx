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

// 默认表单配置模板 - 包含完整的配置示例
const DEFAULT_FORM_CONFIG: FormConfig = {
  groups: {
    hyperparams: [
      {
        title: '基础配置',
        fields: [
          {
            name: ['hyperparams', 'metric'],
            label: '优化指标',
            type: 'select',
            required: true,
            placeholder: '选择优化目标指标',
            tooltip: '模型训练时优化的目标指标',
            defaultValue: 'f1',
            options: [
              { label: 'F1 Score (F1分数)', value: 'f1' },
              { label: 'Precision (精确率)', value: 'precision' },
              { label: 'Recall (召回率)', value: 'recall' },
              { label: 'AUC-ROC (ROC曲线下面积)', value: 'auc' },
            ],
          },
          {
            name: ['hyperparams', 'random_state'],
            label: '随机种子',
            type: 'inputNumber',
            required: true,
            tooltip: '控制随机性，确保实验可复现。相同种子+相同参数=相同结果',
            placeholder: '例: 42',
            defaultValue: 42,
            min: 0,
            max: 2147483647,
            step: 1,
          },
        ],
      },
      {
        title: '搜索空间 (Search Space)',
        fields: [
          {
            name: ['hyperparams', 'search_space', 'contamination'],
            label: '污染率',
            type: 'stringArray',
            required: true,
            tooltip: '预期异常数据占总数据的比例，多个值用逗号分隔',
            placeholder: '例: 0.01,0.05,0.1',
            defaultValue: '0.01,0.05,0.1',
          },
        ],
      },
      {
        title: '',
        subtitle: '高级选项',
        fields: [
          {
            name: ['hyperparams', 'use_feature_engineering'],
            label: '启用特征工程',
            type: 'switch',
            defaultValue: false,
            layout: 'horizontal',
            tooltip: '启用后将生成滞后特征、滚动窗口统计、时间特征等',
          },
        ],
      },
    ],
    preprocessing: [
      {
        title: '数据预处理 (Preprocessing)',
        fields: [
          {
            name: ['preprocessing', 'handle_missing'],
            label: '缺失值处理',
            type: 'select',
            required: true,
            placeholder: '选择缺失值处理方式',
            defaultValue: 'interpolate',
            options: [
              { label: '线性插值 (interpolate)', value: 'interpolate' },
              { label: '前向填充 (ffill)', value: 'ffill' },
              { label: '后向填充 (bfill)', value: 'bfill' },
              { label: '删除 (drop)', value: 'drop' },
              { label: '中位数填充 (median)', value: 'median' },
            ],
          },
          {
            name: ['preprocessing', 'max_missing_ratio'],
            label: '最大缺失率',
            type: 'inputNumber',
            required: true,
            tooltip: '数据缺失比例超过此阈值将拒绝训练',
            placeholder: '0.0 - 1.0',
            defaultValue: 0.3,
            min: 0,
            max: 1,
            step: 0.1,
          },
          {
            name: ['preprocessing', 'label_column'],
            label: '标签列名',
            type: 'input',
            required: true,
            tooltip: '数据集中标签列的名称',
            placeholder: '例: label',
            defaultValue: 'label',
          },
        ],
      },
    ],
    feature_engineering: [
      {
        title: '特征工程 (Feature Engineering)',
        fields: [
          {
            name: ['feature_engineering', 'lag_periods'],
            label: '滞后期',
            type: 'stringArray',
            required: true,
            tooltip: '使用过去N个时间点的值作为特征',
            placeholder: '例: 1,2,3',
            defaultValue: '1,2,3',
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'rolling_windows'],
            label: '滚动窗口大小',
            type: 'stringArray',
            required: true,
            tooltip: '计算滚动窗口统计的窗口大小',
            placeholder: '例: 12,24,48',
            defaultValue: '12,24,48',
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'rolling_features'],
            label: '滚动窗口统计',
            type: 'multiSelect',
            required: true,
            placeholder: '选择统计函数',
            defaultValue: ['mean', 'std', 'min', 'max'],
            options: [
              { label: '均值 (mean)', value: 'mean' },
              { label: '标准差 (std)', value: 'std' },
              { label: '最小值 (min)', value: 'min' },
              { label: '最大值 (max)', value: 'max' },
            ],
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
          {
            name: ['feature_engineering', 'use_temporal_features'],
            label: '时间特征',
            type: 'switch',
            defaultValue: true,
            layout: 'horizontal',
            tooltip: '添加小时、星期、月份等时间特征',
            dependencies: [['hyperparams', 'use_feature_engineering']],
          },
        ],
      },
    ],
  },
};

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
  const [formConfig, setFormConfig] = useState<FormConfig>(DEFAULT_FORM_CONFIG);
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
      setFormConfig(DEFAULT_FORM_CONFIG);
    }
  }, [modalState.isOpen, formData, modalState.type, algorithmType]);

  const loadConfigDetail = async (id: number) => {
    setLoading(true);
    try {
      const data: AlgorithmConfigEntity = await getAlgorithmConfigById(id);
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
        await createAlgorithmConfig(params);
        message.success(t('common.addSuccess'));
      } else {
        await updateAlgorithmConfig(formData!.id, params);
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
    setFormConfig(DEFAULT_FORM_CONFIG);
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
              placeholder="例: ECOD, XGBoost"
              disabled={modalState.type === 'edit'}
            />
          </Form.Item>

          <Form.Item
            name="display_name"
            label={t('algorithmConfig.displayName')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder="例: ECOD 异常检测算法" />
          </Form.Item>

          <Form.Item
            name="scenario_description"
            label={t('algorithmConfig.scenarioDescription')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="描述该算法适用的业务场景"
            />
          </Form.Item>

          <Form.Item
            name="image"
            label={t('algorithmConfig.image')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
            tooltip={t('algorithmConfig.imageTooltip')}
          >
            <Input placeholder="例: registry.example.com/ml/ecod:latest" />
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
