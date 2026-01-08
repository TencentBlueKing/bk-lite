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

const DATASET_MAP: Record<string, string> = {
  'anomaly_detection': 'anomaly_detection_datasets',
  'classification': 'classification_datasets',
  'timeseries_predict': 'timeseries_predict_datasets',
  'log_clustering': 'log_clustering_datasets',
  'rasa': 'rasa_datasets',
  'image_classification': 'image_classification_datasets',
  'object_detection': 'object_detection_datasets',
};

const TRAINDATA_MAP: Record<string, string> = {
  'anomaly_detection': 'anomaly_detection_train_data',
  'classification': 'classification_train_data',
  'timeseries_predict': 'timeseries_predict_train_data',
  'log_clustering': 'log_clustering_train_data',
  'image_classification': 'image_classification_train_data',
  'object_detection': 'object_detection_train_data',
};

const TRAINJOB_MAP: Record<string, string> = {
  'anomaly_detection': 'anomaly_detection_train_jobs',
  'classification': 'classification_train_jobs',
  'timeseries_predict': 'timeseries_predict_train_jobs',
  'log_clustering': 'log_clustering_train_jobs',
  'rasa': 'rasa_pipelines'
};

const SERVING_MAP: Record<string, string> = {
  'anomaly_detection': 'anomaly_detection_servings',
  'classification': 'classification_servings',
  'timeseries_predict': 'timeseries_predict_servings',
  'log_clustering': 'log_clustering_servings',
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

// 异常检测算法场景描述
const ANOMALY_ALGORITHM_SCENARIOS: Record<string, string> = {
  ECOD: '适用于运营指标监控，可检测多维数据中的异常点，如系统资源使用率突增、业务流量异常波动等场景'
};

// 时序预测算法场景描述
const TIMESERIES_ALGORITHM_SCENARIOS: Record<string, string> = {
  GradientBoosting: '短期预测，适用于有滞后特征、波动较大的时序数据',
  RandomForest: '中短期预测，适用于非线性关系、对异常值鲁棒',
  Prophet: '长期预测，适用于明显趋势和季节性（需2-3年数据）'
};

// 日志聚类算法场景描述
const LOG_CLUSTERING_ALGORITHM_SCENARIOS: Record<string, string> = {
  Spell: '基于LCS的流式日志聚类算法，适用于在线日志模板提取，支持动态日志解析和异常检测场景'
};

// 异常检测算法配置 - 用于动态表单渲染
const ANOMALY_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  ECOD: {
    algorithm: 'ECOD',
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
              defaultValue: 'f1',
              options: [
                { label: 'F1 Score (F1分数)', value: 'f1' },
                { label: 'Precision (精确率)', value: 'precision' },
                { label: 'Recall (召回率)', value: 'recall' },
                { label: 'AUC-ROC (ROC曲线下面积)', value: 'auc' }
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
            },
            {
              name: ['hyperparams', 'max_evals'],
              label: '最大评估次数',
              type: 'inputNumber',
              required: true,
              tooltip: '超参数搜索的最大迭代次数，越大搜索越充分但耗时更长',
              placeholder: '推荐: 20-50',
              defaultValue: 30,
              min: 1,
              max: 200
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'contamination'],
              label: '污染率',
              type: 'stringArray',
              required: true,
              tooltip: '预期异常数据占总数据的比例。需根据实际业务场景调整，如告警数据中异常约50%',
              placeholder: '例: 0.49,0.50,0.51,0.52,0.53,0.54,0.55',
              defaultValue: '0.49,0.50,0.51,0.52,0.53,0.54,0.55'
            }
          ]
        },
        {
          title: '',
          subtitle: '特征工程',
          fields: [
            {
              name: ['hyperparams', 'use_feature_engineering'],
              label: '启用特征工程',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '启用后将生成滞后特征、滚动窗口统计、时间特征等，适用于时序异常检测'
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
              tooltip: '数据缺失比例超过此阈值将拒绝训练',
              placeholder: '0.0 - 1.0',
              defaultValue: 0.3,
              min: 0,
              max: 1,
              step: 0.1
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
              tooltip: '使用过去N个时间点的值作为特征，如 [1,2,3] 表示使用前3个时间点',
              placeholder: '例: 1,2,3',
              defaultValue: '1,2,3',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'rolling_windows'],
              label: '滚动窗口大小',
              type: 'stringArray',
              required: true,
              tooltip: '计算滚动窗口统计的窗口大小（小时数），如 [12,24,48] 表示12小时、1天、2天',
              placeholder: '例: 12,24,48',
              defaultValue: '12,24,48',
              dependencies: [['hyperparams', 'use_feature_engineering']]
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
                { label: '最大值 (max)', value: 'max' }
              ],
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_temporal_features'],
              label: '时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '添加小时、星期、月份等时间特征',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_cyclical_features'],
              label: '周期性编码',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '将时间特征转换为正弦/余弦编码，保留周期性',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_diff_features'],
              label: '差分特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '计算相邻时间点的差值，有助于捕捉突变',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'diff_periods'],
              label: '差分期数',
              type: 'stringArray',
              required: true,
              tooltip: '差分的时间间隔，[1] 表示一阶差分',
              placeholder: '例: 1',
              defaultValue: '1',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_diff_features']]
            }
          ]
        }
      ]
    }
  }
};

// 时序预测算法配置 - 用于动态表单渲染
const TIMESERIES_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  Prophet: {
    algorithm: 'Prophet',
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
              defaultValue: 'rmse',
              options: [
                { label: 'RMSE (均方根误差)', value: 'rmse' },
                { label: 'MAE (平均绝对误差)', value: 'mae' },
                { label: 'MAPE (平均绝对百分比误差)', value: 'mape' }
              ]
            },
            {
              name: ['hyperparams', 'growth'],
              label: '增长模式',
              type: 'select',
              required: true,
              tooltip: 'linear=线性增长(默认)，logistic=逻辑增长(需设置容量上限)',
              placeholder: '选择增长模式',
              defaultValue: 'linear',
              options: [
                { label: '线性增长 (linear)', value: 'linear' },
                { label: '逻辑增长 (logistic)', value: 'logistic' }
              ]
            },
            {
              name: ['hyperparams', 'yearly_seasonality'],
              label: '年度季节性',
              type: 'select',
              required: true,
              tooltip: 'auto=自动检测（数据>=2年则启用），true=强制启用，false=禁用',
              placeholder: '选择年度季节性',
              defaultValue: 'auto',
              options: [
                { label: '自动 (auto)', value: 'auto' },
                { label: '启用 (true)', value: 'true' },
                { label: '禁用 (false)', value: 'false' }
              ]
            },
            {
              name: ['hyperparams', 'weekly_seasonality'],
              label: '周季节性',
              type: 'select',
              required: true,
              tooltip: 'auto=自动检测（数据>=2周则启用），日度数据建议启用',
              placeholder: '选择周季节性',
              defaultValue: 'auto',
              options: [
                { label: '自动 (auto)', value: 'auto' },
                { label: '启用 (true)', value: 'true' },
                { label: '禁用 (false)', value: 'false' }
              ]
            },
            {
              name: ['hyperparams', 'daily_seasonality'],
              label: '日季节性',
              type: 'select',
              required: true,
              tooltip: 'auto=自动检测，小时级数据建议启用，日度及以上数据建议禁用',
              placeholder: '选择日季节性',
              defaultValue: 'auto',
              options: [
                { label: '自动 (auto)', value: 'auto' },
                { label: '启用 (true)', value: 'true' },
                { label: '禁用 (false)', value: 'false' }
              ]
            },
            {
              name: ['hyperparams', 'seasonality_prior_scale'],
              label: '季节性强度',
              type: 'inputNumber',
              required: true,
              tooltip: '季节性强度的先验尺度。越大=季节性波动越灵活，越小=越平滑保守',
              placeholder: '推荐范围: 0.01 - 10',
              defaultValue: 10.0,
              min: 0.01,
              max: 100,
              step: 0.01
            },
            {
              name: ['hyperparams', 'holidays_prior_scale'],
              label: '节假日强度',
              type: 'inputNumber',
              required: true,
              tooltip: '节假日效应的先验尺度，仅在提供节假日数据时有效',
              placeholder: '推荐范围: 0.01 - 10',
              defaultValue: 10.0,
              min: 0.01,
              max: 100,
              step: 0.01
            },
            {
              name: ['hyperparams', 'n_changepoints'],
              label: '变点数量',
              type: 'inputNumber',
              required: true,
              tooltip: 'Prophet 自动在训练数据前 80% 均匀分布的潜在趋势变点数量',
              placeholder: '推荐: 10-50',
              defaultValue: 25,
              min: 1,
              max: 200
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'seasonality_mode'],
              label: '季节性模式',
              type: 'stringArray',
              required: true,
              tooltip: 'additive=加性(趋势+季节性，波动固定)，multiplicative=乘性(趋势×季节性，波动随趋势变化)',
              placeholder: '例: additive,multiplicative',
              defaultValue: 'additive,multiplicative'
            },
            {
              name: ['hyperparams', 'search_space', 'changepoint_prior_scale'],
              label: '变点灵活性',
              type: 'stringArray',
              required: true,
              tooltip: '最重要的超参数！控制趋势变化灵活度。大值(0.5)=灵活但易过拟合，小值(0.001)=平滑但可能欠拟合',
              placeholder: '例: 0.001,0.01,0.05,0.1,0.5',
              defaultValue: '0.001,0.01,0.05,0.1,0.5'
            },
            {
              name: ['hyperparams', 'search_space', 'seasonality_prior_scale'],
              label: '季节性强度搜索',
              type: 'stringArray',
              required: true,
              tooltip: '搜索最优的季节性强度（会覆盖上面的固定值）',
              placeholder: '例: 0.01,0.1,1.0,10.0',
              defaultValue: '0.01,0.1,1.0,10.0'
            },
            {
              name: ['hyperparams', 'search_space', 'holidays_prior_scale'],
              label: '节假日强度搜索',
              type: 'stringArray',
              required: true,
              tooltip: '搜索最优的节假日效应强度',
              placeholder: '例: 0.01,0.1,1.0,10.0',
              defaultValue: '0.01,0.1,1.0,10.0'
            },
            {
              name: ['hyperparams', 'search_space', 'n_changepoints'],
              label: '变点数量搜索',
              type: 'stringArray',
              required: true,
              tooltip: '搜索最优的变点数量（会覆盖上面的固定值）',
              placeholder: '例: 10,25,50,100',
              defaultValue: '10,25,50,100'
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
      ]
    }
  },
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
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'rolling_windows'],
              label: '滚动窗口大小',
              type: 'stringArray',
              required: true,
              placeholder: '例: 7,14,30',
              defaultValue: '7,14,30',
              dependencies: [['hyperparams', 'use_feature_engineering']]
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
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_temporal_features'],
              label: '时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_cyclical_features'],
              label: '周期性编码',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_diff_features'],
              label: '差分特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'diff_periods'],
              label: '差分期数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1',
              defaultValue: '1',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_diff_features']]
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
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'rolling_windows'],
              label: '滚动窗口大小',
              type: 'stringArray',
              required: true,
              placeholder: '例: 7,14,30',
              defaultValue: '7,14,30',
              dependencies: [['hyperparams', 'use_feature_engineering']]
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
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_temporal_features'],
              label: '时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_cyclical_features'],
              label: '周期性编码',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_diff_features'],
              label: '差分特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'diff_periods'],
              label: '差分期数',
              type: 'stringArray',
              required: true,
              placeholder: '例: 1',
              defaultValue: '1',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_diff_features']]
            }
          ]
        }
      ]
    }
  }
};

// 日志聚类算法配置 - 用于动态表单渲染
const LOG_CLUSTERING_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  Spell: {
    algorithm: 'Spell',
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
              defaultValue: 'template_quality_score',
              options: [
                { label: '模板质量评分 (template_quality_score)', value: 'template_quality_score' },
                { label: '模板数量 (num_templates)', value: 'num_templates' },
                { label: '覆盖率 (coverage_rate)', value: 'coverage_rate' },
                { label: '模板多样性 (template_diversity)', value: 'template_diversity' }
              ],
              tooltip: 'template_quality_score=综合质量评分（推荐），num_templates=模板数量，coverage_rate=覆盖率，template_diversity=多样性'
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
            },
            {
              name: ['hyperparams', 'max_evals'],
              label: '最大评估次数',
              type: 'inputNumber',
              required: true,
              tooltip: '超参数搜索的最大迭代次数。设为 0 跳过搜索，直接使用搜索空间中的第一个值。大于 0 时自动启用早停机制',
              placeholder: '推荐: 20-50',
              defaultValue: 50,
              min: 0,
              max: 200
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'tau'],
              label: 'LCS 相似度阈值',
              type: 'stringArray',
              required: true,
              tooltip: 'Spell LCS 相似度阈值。范围 0-1，越大越严格（生成更多模板）。0.3-0.4=宽松匹配，0.5=默认推荐，0.6-0.7=严格匹配',
              placeholder: '例: 0.4,0.45,0.5,0.55,0.6',
              defaultValue: '0.4,0.45,0.5,0.55,0.6'
            }
          ]
        },
        {
          title: '',
          subtitle: '特征工程',
          fields: [
            {
              name: ['hyperparams', 'use_feature_engineering'],
              label: '启用特征工程',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: 'Spell/Drain 等模板方法通常不需要（设为 false）；LogBERT/DeepLog 等深度学习方法建议启用（设为 true）'
            }
          ]
        }
      ],
      preprocessing: [
        {
          title: '日志预处理 (Preprocessing)',
          fields: [
            {
              name: ['preprocessing', 'remove_digits'],
              label: '替换数字',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '是否将数字替换为 <NUM>。启用可提高模板泛化能力'
            },
            {
              name: ['preprocessing', 'remove_special_chars'],
              label: '移除特殊字符',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '是否移除特殊字符（保留字母数字和基本分隔符）'
            },
            {
              name: ['preprocessing', 'lowercase'],
              label: '转小写',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '是否转小写。建议保持原样以保留大小写语义'
            }
          ]
        }
      ],
      feature_engineering: [
        {
          title: '特征工程 (Feature Engineering)',
          subtitle: '文本特征',
          fields: [
            {
              name: ['feature_engineering', 'text_features', 'enable'],
              label: '启用文本特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '提取文本统计特征（轻量级，计算快速）',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'text_features', 'features'],
              label: '文本特征类型',
              type: 'multiSelect',
              required: true,
              placeholder: '选择要提取的文本特征',
              defaultValue: ['length', 'token_count', 'digit_ratio', 'special_char_ratio', 'uppercase_ratio', 'avg_token_length'],
              options: [
                { label: '日志长度 (length)', value: 'length' },
                { label: 'Token数量 (token_count)', value: 'token_count' },
                { label: '数字占比 (digit_ratio)', value: 'digit_ratio' },
                { label: '特殊字符占比 (special_char_ratio)', value: 'special_char_ratio' },
                { label: '大写字母占比 (uppercase_ratio)', value: 'uppercase_ratio' },
                { label: '平均Token长度 (avg_token_length)', value: 'avg_token_length' }
              ],
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'text_features', 'enable']]
            }
          ]
        },
        {
          title: '',
          subtitle: '时间特征',
          fields: [
            {
              name: ['feature_engineering', 'time_features', 'enable'],
              label: '启用时间特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '提取时间特征（需要日志数据包含时间戳列）',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'time_features', 'datetime_column'],
              label: '时间戳列名',
              type: 'input',
              required: true,
              placeholder: '例: timestamp',
              defaultValue: 'timestamp',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'time_features', 'enable']]
            },
            {
              name: ['feature_engineering', 'time_features', 'cyclical_features'],
              label: '周期性时间特征',
              type: 'multiSelect',
              required: true,
              placeholder: '选择周期性特征（会自动添加 sin/cos 编码）',
              defaultValue: ['hour', 'day_of_week'],
              options: [
                { label: '小时 (hour)', value: 'hour' },
                { label: '星期 (day_of_week)', value: 'day_of_week' },
                { label: '日期 (day)', value: 'day' },
                { label: '月份 (month)', value: 'month' },
                { label: '周数 (week)', value: 'week' },
                { label: '分钟 (minute)', value: 'minute' },
                { label: '秒 (second)', value: 'second' }
              ],
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'time_features', 'enable']]
            },
            {
              name: ['feature_engineering', 'time_features', 'interval_features'],
              label: '时间间隔特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '提取相邻日志的时间差特征',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'time_features', 'enable']]
            }
          ]
        },
        {
          title: '',
          subtitle: '日志级别特征',
          fields: [
            {
              name: ['feature_engineering', 'level_features', 'enable'],
              label: '启用日志级别特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '提取日志级别特征（需要日志数据包含级别列）',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'level_features', 'level_column'],
              label: '日志级别列名',
              type: 'input',
              required: true,
              placeholder: '例: level',
              defaultValue: 'level',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'level_features', 'enable']]
            }
          ]
        },
        {
          title: '',
          subtitle: '频率特征',
          fields: [
            {
              name: ['feature_engineering', 'frequency_features', 'enable'],
              label: '启用频率特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '提取日志出现频率和罕见度特征（轻量级）',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'frequency_features', 'window_size'],
              label: '时间窗口大小',
              type: 'input',
              required: true,
              placeholder: "例: 5min, 1H, 1D",
              defaultValue: '5min',
              tooltip: '用于计算窗口内日志频率。格式: 5min, 1H, 1D 等',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'frequency_features', 'enable']]
            }
          ]
        },
        {
          title: '',
          subtitle: '序列特征',
          fields: [
            {
              name: ['feature_engineering', 'sequence_features', 'enable'],
              label: '启用序列特征',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '提取日志序列特征（中等开销，捕捉日志前后关系）',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'sequence_features', 'window_size'],
              label: '滑动窗口大小',
              type: 'inputNumber',
              required: true,
              placeholder: '例: 10',
              defaultValue: 10,
              min: 1,
              tooltip: '用于统计窗口内的日志重复（需要保持日志时间顺序）',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'sequence_features', 'enable']]
            }
          ]
        },
        {
          title: '',
          subtitle: '语义特征',
          fields: [
            {
              name: ['feature_engineering', 'semantic_features', 'enable'],
              label: '启用语义特征',
              type: 'switch',
              defaultValue: false,
              layout: 'horizontal',
              tooltip: '提取语义特征（TF-IDF/Word2Vec/BERT），计算密集型，仅深度学习方法建议启用',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'semantic_features', 'method'],
              label: '语义特征方法',
              type: 'select',
              required: true,
              placeholder: '选择语义特征提取方法',
              defaultValue: 'tfidf',
              options: [
                { label: 'TF-IDF', value: 'tfidf' },
                { label: 'Word2Vec', value: 'word2vec' },
                { label: 'BERT', value: 'bert' }
              ],
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'semantic_features', 'enable']]
            },
            {
              name: ['feature_engineering', 'semantic_features', 'max_features'],
              label: '最大特征维度',
              type: 'inputNumber',
              required: true,
              placeholder: '例: 100',
              defaultValue: 100,
              min: 10,
              max: 1000,
              tooltip: 'TF-IDF 向量的最大维度',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'semantic_features', 'enable']]
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
  ANOMALY_ALGORITHM_CONFIGS,
  ANOMALY_ALGORITHM_SCENARIOS,
  TIMESERIES_ALGORITHM_CONFIGS,
  TIMESERIES_ALGORITHM_SCENARIOS,
  LOG_CLUSTERING_ALGORITHM_CONFIGS,
  LOG_CLUSTERING_ALGORITHM_SCENARIOS,
  TRAINJOB_MAP,
  TYPE_FILE_MAP,
  SERVING_MAP,
  DATASET_MAP,
  TRAINDATA_MAP
}