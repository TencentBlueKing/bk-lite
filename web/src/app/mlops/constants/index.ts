import { LevelMap, Option, } from "@/app/mlops/types";
import { AlgorithmParam } from "@/app/mlops/types/task";

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

const TIMESERIES_PREDICT_ALGORITHMS_PARAMS: Record<string, AlgorithmParam[]> = {
  'Prophet': []
};

const TIMESERIES_PREDICT_ALGORITHMS_TYPE: Record<string, any> = {
  'Prophet': {}
};

const ALGORITHMS_PARAMS: Record<string, AlgorithmParam[]> = {
  ...ANOMALY_ALGORITHMS_PARAMS,
  ...LOG_CLUSTERING_ALGORITHMS_PARAMS,
  ...TIMESERIES_PREDICT_ALGORITHMS_PARAMS
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
  PIPELINE_OPTIONS,
  POLICIES_OPTIONS,
  PIPELINE_TYPE_OPTIONS,
  ANOMALY_ALGORITHMS_PARAMS,
  LOG_CLUSTERING_ALGORITHMS_PARAMS,
  TIMESERIES_PREDICT_ALGORITHMS_PARAMS
}