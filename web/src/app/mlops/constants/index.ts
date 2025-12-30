import { LevelMap, Option, } from "@/app/mlops/types";
import { AlgorithmParam, AlgorithmConfig } from "@/app/mlops/types/task";

const LEVEL_MAP: LevelMap = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
};

const TRAIN_STATUS_MAP = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error'
};

const TYPE_CONTENT: Record<string, any> = {
  is_test_data: 'test',
  is_train_data: 'train',
  is_val_data: 'validate',
};

const TYPE_COLOR: Record<string, any> = {
  is_test_data: 'orange',
  is_train_data: 'blue',
  is_val_data: 'green',
};

const TRAIN_TEXT = {
  pending: 'notStarted',
  running: 'inProgress',
  completed: 'completed',
  failed: 'failed'
};

const ANOMALY_ALGORITHMS_PARAMS: Record<string, AlgorithmParam[]> = {
  'RandomForest': [
    { name: 'n_estimators', type: 'randint', default: [100, 500] },
    { name: 'max_depth', type: 'randint', default: [10, 50] },
    { name: 'min_samples_split', type: 'randint', default: [2, 10] },
    { name: 'min_samples_leaf', type: 'randint', default: [1, 10] },
    {
      name: 'max_features',
      type: 'choice',
      default: ['none'],
      options: [
        { label: 'sqrt', value: 'sqrt' },
        { label: 'log2', value: 'log2' },
        { label: 'none', value: 'none' },
      ]
    },
    {
      name: 'bootstrap',
      type: 'choice',
      default: ['false'],
      options: [
        { label: 'true', value: 'true' },
        { label: 'false', value: 'false' },
      ]
    },
    {
      name: 'class_weight',
      type: 'choice',
      default: ['none'],
      options: [
        { label: 'balanced', value: 'balanced' },
        { label: 'balanced_subsample', value: 'balanced_subsample' },
        { label: 'none', value: 'none' },
      ]
    },
  ],
};

const ANOMALY_ALGORITHMS_TYPE: Record<string, any> = {
  'RandomForest': {
    n_estimators: 'randint',
    max_depth: 'randint',
    min_samples_split: 'randint',
    min_samples_leaf: 'randint',
    max_features: 'choice',
    bootstrap: 'choice',
    class_weight: 'choice'
  }
};

const LOG_CLUSTERING_ALGORITHMS_PARAMS: Record<string, AlgorithmParam[]> = {
  'KMeans': [],
  'DBSCAN': [],
  'AgglomerativeClustering': [],
  'Drain': [],
  'LogCluster': [],
};

const LOG_CLUSTERING_ALGORITHMS_TYPE: Record<string, any> = {
  'KMeans': {},
  'DBSCAN': {},
  'AgglomerativeClustering': {},
  'Drain': {},
  'LogCluster': {},
};

const TIMESERIES_PREDICT_ALGORITHMS_TYPE: Record<string, any> = {
  // 'Prophet': {},
  'GradientBoosting': {
    metric: 'choice',
    learning_rate: 'randint',
    max_depth: 'randint',
    min_samples_split: 'randint',
    min_samples_leaf: 'randint',
    subsample: 'randint',
    lag_features: 'randint',
    n_estimators: 'randint',
    feature_engineering: 'choice'
  }
};

const ALGORITHMS_PARAMS: Record<string, AlgorithmParam[]> = {
  ...ANOMALY_ALGORITHMS_PARAMS,
  ...LOG_CLUSTERING_ALGORITHMS_PARAMS,
};

const ALGORITHMS_TYPE: Record<string, any> = {
  ...ANOMALY_ALGORITHMS_TYPE,
  ...LOG_CLUSTERING_ALGORITHMS_TYPE,
  ...TIMESERIES_PREDICT_ALGORITHMS_TYPE
};

type TRAIN_STATUS = 'not_started' | 'in_progress' | 'completed' | 'failed';

const TOKENIZER_PARAMS = [
  {
    name: 'intent_tokenization_flag',
    type: 'boolean',
    dest: '意图分词'
  },
  {
    name: 'intent_split_symbol',
    type: 'string',
    dest: '意图分割符号'
  },
  {
    name: 'token_pattern',
    type: 'RegExp',
    dest: '正则表达式模式'
  }
]

const RASA_CONFIG: Record<string, {
  name: string;
  type: string;
  options?: Option[],
  dest?: string
}[]> = {
  'JiebaTokenizer': [
    ...TOKENIZER_PARAMS
  ],
  'RegexFeaturizer': [
    {
      name: 'use_word_boundaries',
      type: 'boolean',
      dest: '是否使用词边界'
    },
    {
      name: 'case_sensitive',
      type: 'option',
      options: [
        { label: 'True', value: 'True' },
        { label: 'False', value: 'False' },
      ],
      dest: '是否大小写敏感'
    },
    {
      name: 'number_additional_patterns',
      type: 'number',
      dest: '额外数量模式'
    }
  ],
  'LanguageModelFeaturizer': [
    {
      name: 'model_name',
      type: 'stirng',
      dest: '模型名称'
    },
    {
      name: 'model_weights',
      type: 'string',
      dest: '预训练权重'
    },
    {
      name: 'cache_dir',
      type: 'string',
      dest: '缓存目录'
    }
  ],
  'LexicalSyntacticFeaturizer': [],
  'CountVectorsFeaturizer': [
    {
      name: 'analyzer',
      type: 'option',
      options: [
        { label: 'word', value: 'word' },
        { label: 'char', value: 'char' },
        { label: 'char_wb', value: 'char_wb' },
      ],
      dest: '分析器类型'
    },
    {
      name: 'min_ngram',
      type: 'number',
      dest: '最小n-gram长度'
    },
    {
      name: 'max_ngram',
      type: 'number',
      dest: '最大n-gram长度'
    }
  ],
  'DIETClassifier': [
    {
      name: 'epochs',
      type: 'number',
      dest: '训练轮数'
    },
    {
      name: 'constrain_similarities',
      type: 'boolean',
      dest: '约束相似度'
    },
    {
      name: 'evaluate_on_number_of_examples',
      type: 'number',
      dest: '评估样本数'
    },
    {
      name: 'evaluate_every_number_of_epochs',
      type: 'number',
      dest: '评估频率'
    },
    {
      name: 'number_of_transformer_layers',
      type: 'number',
      dest: 'Transformer层数'
    },
    {
      name: 'transformer_size',
      type: 'number',
      dest: 'Transformer维度'
    },
    {
      name: 'number_of_attention_heads',
      type: 'number',
      dest: '注意力头数'
    },
    {
      name: 'learning_rate',
      type: 'number',
      dest: '学习率'
    },
    {
      name: 'drop_rate',
      type: 'number',
      dest: '全局丢弃率'
    },
    {
      name: 'tensorboard_log_directory',
      type: 'string',
      dest: 'TensorBoard日志目录'
    },
    {
      name: 'tensorboard_log_level',
      type: 'option',
      options: [
        { label: 'epoch', value: 'epoch' },
        { label: 'minibatch', value: 'minibatch' },
      ],
      dest: '日志级别'
    },
  ],
  'FallbackClassifier': [
    {
      name: 'threshold',
      type: 'number',
      dest: '置信度阈值'
    },
    {
      name: 'ambiguity_threshold',
      type: 'number',
      dest: '歧义阈值'
    }
  ],
  'ResponseSelector': [
    {
      name: 'epochs',
      type: 'number',
      dest: '训练轮数'
    }
  ],
  'RegexEntityExtractor': [
    {
      name: 'case_sensitive',
      type: 'option',
      options: [
        { label: 'True', value: 'True' },
        { label: 'False', value: 'False' },
      ],
      dest: '大小写敏感'
    },
    {
      name: 'use_lookup_tables',
      type: 'option',
      options: [
        { label: 'True', value: 'True' },
        { label: 'False', value: 'False' },
      ],
      dest: '使用查找表',
    },
    {
      name: 'use_regexes',
      type: 'option',
      options: [
        { label: 'True', value: 'True' },
        { label: 'False', value: 'False' },
      ],
      dest: '使用正则表达式'
    },
    {
      name: 'use_word_boundaries',
      type: 'option',
      options: [
        { label: 'True', value: 'True' },
        { label: 'False', value: 'False' },
      ],
      dest: '使用词边界'
    }
  ],
  'MemoizationPolicy': [],
  'TEDPolicy': [
    {
      name: 'epochs',
      type: 'number',
      dest: '训练轮数'
    },
    {
      name: 'max_history',
      type: 'number',
      dest: '最大对话历史长度'
    },
    {
      name: 'constrain_similarities',
      type: 'boolean',
      dest: '约束相似度'
    },
    {
      name: 'evaluate_on_number_of_examples',
      type: 'number',
      dest: '评估频率'
    },
    {
      name: 'evaluate_every_number_of_epochs',
      type: 'number',
      dest: '评估样本数'
    },
    {
      name: 'tensorboard_log_directory',
      type: 'string',
      dest: 'TensorBoard日志目录'
    },
    {
      name: 'tensorboard_log_level',
      type: 'option',
      options: [
        { label: 'epoch', value: 'epoch' },
        { label: 'minibatch', value: 'minibatch' },
      ],
      dest: '日志级别'
    }
  ],
  'RulePolicy': [
    {
      name: 'core_fallback_threshold',
      type: 'number',
      dest: '核心回退阈值'
    },
    {
      name: 'core_fallback_action_name',
      type: 'string',
      dest: '回退动作名称'
    }
  ]
}

// Pipeline 类型选项
const PIPELINE_TYPE_OPTIONS: Option[] = [
  { label: '分词器', value: 'tokenizer' },
  { label: '特征提取器', value: 'featurizers' },
  { label: '分类器', value: 'classifier' },
  { label: '实体提取器', value: 'extractor' },
  { label: '响应选择器', value: 'selector' }
];

// Pipeline 组件选项
const PIPELINE_OPTIONS: Record<string, Option[]> = {
  'tokenizer': [
    { label: 'JiebaTokenizer', value: 'JiebaTokenizer' },
    // { label: 'WhitespaceTokenizer', value: 'WhitespaceTokenizer' },
    // { label: 'SpacyTokenizer', value: 'SpacyTokenizer' },
  ],
  'featurizers': [
    { label: 'RegexFeaturizer', value: 'RegexFeaturizer' },
    { label: 'CountVectorsFeaturizer', value: 'CountVectorsFeaturizer' },
    { label: 'LexicalSyntacticFeaturizer', value: 'LexicalSyntacticFeaturizer' },
    { label: 'LanguageModelFeaturizer', value: 'LanguageModelFeaturizer' },
    // { label: 'SpacyFeaturizer', value: 'SpacyFeaturizer' },
  ],
  'classifier': [
    { label: 'DIETClassifier', value: 'DIETClassifier' },
    // { label: 'SklearnIntentClassifier', value: 'SklearnIntentClassifier' },
    // { label: 'KeywordIntentClassifier', value: 'KeywordIntentClassifier' },
    { label: 'FallbackClassifier', value: 'FallbackClassifier' },
  ],
  'extractor': [
    // { label: 'CRFEntityExtractor', value: 'CRFEntityExtractor' },
    // { label: 'SpacyEntityExtractor', value: 'SpacyEntityExtractor' },
    // { label: 'DucklingEntityExtractor', value: 'DucklingEntityExtractor' },
    { label: 'RegexEntityExtractor', value: 'RegexEntityExtractor' },
  ],
  'selector': [
    { label: 'ResponseSelector', value: 'ResponseSelector' },
  ]
};

// Policies 选项
const POLICIES_OPTIONS: Option[] = [
  { label: 'MemoizationPolicy', value: 'MemoizationPolicy' },
  // { label: 'AugmentedMemoizationPolicy', value: 'AugmentedMemoizationPolicy' },
  { label: 'TEDPolicy', value: 'TEDPolicy' },
  // { label: 'UnexpecTEDIntentPolicy', value: 'UnexpecTEDIntentPolicy' },
  { label: 'RulePolicy', value: 'RulePolicy' },
];

const TRAINJOB_MAP: Record<string, string> = {
  'anomaly_detection': 'anomaly_detection_train_jobs',
  'classification': 'classification_train_jobs',
  'timeseries_predict': 'timeseries_predict_train_jobs',
  'log_clustering': 'log_clustering_train_jobs',
  'rasa': 'rasa_pipelines'
};

const TYPE_FILE_MAP: Record<string, any> = {
  'anomaly_detection': 'csv',
  'log_clustering': 'txt',
  'timeseries_predict': 'csv',
  'classification': 'csv',
  'image_classification': 'image',
  'object_detection': 'image'
};

const RASA_MENUS = [
  {
    menu: 'intent',
    icon: 'suanwangyitu',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'entity',
    icon: 'shitishu',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'action',
    icon: 'dongzuozu',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'response',
    icon: 'huifu',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'slot',
    icon: 'bianliang-xin',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'form',
    icon: 'wodegushi',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'rule',
    icon: 'guizepeizhi',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
  {
    menu: 'story',
    icon: 'wodegushi',
    content: '用来描述对话流程的关键部分，他相当于对话机器人的"训练样本"，帮助模型学习如何在不同的用户输入下选择正确的动作或回复'
  },
];

// 时序预测算法配置 - 用于动态表单渲染
const TIMESERIES_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  GradientBoosting: {
    algorithm: 'GradientBoosting',
    groups: {
      hyperparams: [
        {
          title: '训练配置',
          fields: [
            {
              name: ['hyperparams', 'metric'],
              label: '优化指标',
              type: 'select',
              required: true,
              placeholder: '选择优化目标指标',
              defaultValue: 'rmse',
              options: [
                { label: 'RMSE (均方根误差)', value: 'rmse' },
                { label: 'MAE (平均绝对误差)', value: 'mae' },
                { label: 'MAPE (平均绝对百分比误差)', value: 'mape' }
              ]
            },
            {
              name: ['hyperparams', 'random_state'],
              label: '随机种子',
              type: 'inputNumber',
              required: true,
              tooltip: '控制随机性，确保实验可复现。相同种子+相同参数=相同结果',
              placeholder: '例: 42',
              defaultValue: 42,
              min: 0
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          subtitle: '树结构参数',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'n_estimators'],
              label: '树的数量',
              type: 'stringArray',
              required: true,
              placeholder: '例: 50,100,200,300',
              defaultValue: '50,100,200,300'
            },
            {
              name: ['hyperparams', 'search_space', 'max_depth'],
              label: '树最大深度',
              type: 'stringArray',
              required: true,
              placeholder: '例: 3,5,7,10',
              defaultValue: '3,5,7,10'
            },
            {
              name: ['hyperparams', 'search_space', 'learning_rate'],
              label: '学习率',
              type: 'stringArray',
              required: true,
              placeholder: '例: 0.01,0.05,0.1,0.2',
              defaultValue: '0.01,0.05,0.1,0.2'
            }
          ]
        },
        {
          title: '',
          subtitle: '采样控制参数',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'min_samples_split'],
              label: '最小分裂样本数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 2,5,10',
              defaultValue: '2,5,10'
            },
            {
              name: ['hyperparams', 'search_space', 'min_samples_leaf'],
              label: '叶节点最小样本数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1,2,4',
              defaultValue: '1,2,4'
            },
            {
              name: ['hyperparams', 'search_space', 'subsample'],
              label: '子采样比例',
              type: 'stringArray',
              required: true,
              placeholder: '例: 0.7,0.8,0.9,1.0',
              defaultValue: '0.7,0.8,0.9,1.0'
            }
          ]
        },
        {
          title: '',
          subtitle: '特征参数',
          fields: [
            {
              name: ['hyperparams', 'use_feature_engineering'],
              label: '启用特征工程',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '启用完整特征工程（滚动窗口、时间特征等）或仅使用简单滞后特征'
            },
            {
              name: ['hyperparams', 'search_space', 'lag_features'],
              label: '滞后特征数量',
              type: 'stringArray',
              required: true,
              placeholder: '例: 6,12,24',
              defaultValue: '6,12,24',
              tooltip: '仅在 use_feature_engineering=false 时使用'
            }
          ]
        }
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
                { label: '中位数填充 (median)', value: 'median' }
              ]
            },
            {
              name: ['preprocessing', 'max_missing_ratio'],
              label: '最大缺失率',
              type: 'inputNumber',
              required: true,
              placeholder: '0.0 - 1.0',
              defaultValue: 0.3,
              min: 0,
              max: 1,
              step: 0.1
            },
            {
              name: ['preprocessing', 'interpolation_limit'],
              label: '插值限制',
              type: 'inputNumber',
              required: true,
              placeholder: '最多填充的连续缺失点数',
              defaultValue: 3,
              min: 1
            }
          ]
        }
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
              placeholder: '例: 1,2,3,7,14',
              defaultValue: '1,2,3,7,14',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'rolling_windows'],
              label: '滚动窗口大小',
              type: 'stringArray',
              required: true,
              placeholder: '例: 7,14,30',
              defaultValue: '7,14,30',
              dependencies: ['hyperparams', 'use_feature_engineering']
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
                { label: '中位数 (median)', value: 'median' },
                { label: '求和 (sum)', value: 'sum' }
              ],
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_temporal_features'],
              label: '时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_cyclical_features'],
              label: '周期性编码',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_diff_features'],
              label: '差分特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'diff_periods'],
              label: '差分期数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1',
              defaultValue: '1',
              dependencies: ['feature_engineering', 'use_diff_features']
            }
          ]
        }
      ]
    }
  },
  RandomForest: {
    algorithm: 'RandomForest',
    groups: {
      hyperparams: [
        {
          title: '训练配置',
          fields: [
            {
              name: ['hyperparams', 'metric'],
              label: '优化指标',
              type: 'select',
              required: true,
              placeholder: '选择优化目标指标',
              defaultValue: 'rmse',
              options: [
                { label: 'RMSE (均方根误差)', value: 'rmse' },
                { label: 'MAE (平均绝对误差)', value: 'mae' },
                { label: 'MAPE (平均绝对百分比误差)', value: 'mape' }
              ]
            },
            {
              name: ['hyperparams', 'random_state'],
              label: '随机种子',
              type: 'inputNumber',
              required: true,
              tooltip: '控制随机性，确保实验可复现。相同种子+相同参数=相同结果',
              placeholder: '例: 42',
              defaultValue: 42,
              min: 0
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          subtitle: '树结构参数',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'n_estimators'],
              label: '树的数量',
              type: 'stringArray',
              required: true,
              placeholder: '例: 50,100,200,300',
              defaultValue: '50,100,200,300'
            },
            {
              name: ['hyperparams', 'search_space', 'max_depth'],
              label: '树最大深度',
              type: 'stringArray',
              required: true,
              placeholder: '例: 3,5,7,10',
              defaultValue: '3,5,7,10'
            },
            {
              name: ['hyperparams', 'search_space', 'min_samples_split'],
              label: '最小分裂样本数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 2,5,10',
              defaultValue: '2,5,10'
            },
            {
              name: ['hyperparams', 'search_space', 'min_samples_leaf'],
              label: '叶节点最小样本数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1,2,4',
              defaultValue: '1,2,4'
            },
            {
              name: ['hyperparams', 'search_space', 'max_features'],
              label: '最大特征数',
              type: 'stringArray',
              required: true,
              tooltip: 'sqrt=特征数的平方根(推荐)，log2=特征数的对数(更保守)',
              placeholder: '例: sqrt,log2',
              defaultValue: 'sqrt,log2'
            }
          ]
        },
        {
          title: '',
          subtitle: '特征参数',
          fields: [
            {
              name: ['hyperparams', 'use_feature_engineering'],
              label: '启用特征工程',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '启用完整特征工程（滚动窗口、时间特征等）或仅使用简单滞后特征'
            },
            {
              name: ['hyperparams', 'search_space', 'lag_features'],
              label: '滞后特征数量',
              type: 'stringArray',
              required: true,
              placeholder: '例: 6,12,24',
              defaultValue: '6,12,24',
              tooltip: '仅在 use_feature_engineering=false 时使用'
            }
          ]
        }
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
                { label: '中位数填充 (median)', value: 'median' }
              ]
            },
            {
              name: ['preprocessing', 'max_missing_ratio'],
              label: '最大缺失率',
              type: 'inputNumber',
              required: true,
              placeholder: '0.0 - 1.0',
              defaultValue: 0.3,
              min: 0,
              max: 1,
              step: 0.1
            },
            {
              name: ['preprocessing', 'interpolation_limit'],
              label: '插值限制',
              type: 'inputNumber',
              required: true,
              placeholder: '最多填充的连续缺失点数',
              defaultValue: 3,
              min: 1
            }
          ]
        }
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
              placeholder: '例: 1,2,3,7,14',
              defaultValue: '1,2,3,7,14',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'rolling_windows'],
              label: '滚动窗口大小',
              type: 'stringArray',
              required: true,
              placeholder: '例: 7,14,30',
              defaultValue: '7,14,30',
              dependencies: ['hyperparams', 'use_feature_engineering']
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
                { label: '中位数 (median)', value: 'median' },
                { label: '求和 (sum)', value: 'sum' }
              ],
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_temporal_features'],
              label: '时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_cyclical_features'],
              label: '周期性编码',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'use_diff_features'],
              label: '差分特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: ['hyperparams', 'use_feature_engineering']
            },
            {
              name: ['feature_engineering', 'diff_periods'],
              label: '差分期数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1',
              defaultValue: '1',
              dependencies: ['feature_engineering', 'use_diff_features']
            }
          ]
        }
      ]
    }
  }
};


export {
  LEVEL_MAP,
  TRAIN_STATUS_MAP,
  TRAIN_TEXT,
  TYPE_CONTENT,
  ALGORITHMS_PARAMS,
  ALGORITHMS_TYPE,
  type TRAIN_STATUS,
  TYPE_COLOR,
  RASA_CONFIG,
  RASA_MENUS,
  PIPELINE_OPTIONS,
  POLICIES_OPTIONS,
  PIPELINE_TYPE_OPTIONS,
  ANOMALY_ALGORITHMS_PARAMS,
  LOG_CLUSTERING_ALGORITHMS_PARAMS,
  TIMESERIES_ALGORITHM_CONFIGS,
  TRAINJOB_MAP,
  TYPE_FILE_MAP
}