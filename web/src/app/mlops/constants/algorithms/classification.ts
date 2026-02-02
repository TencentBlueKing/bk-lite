import { AlgorithmConfig } from "@/app/mlops/types/task";

// Classification 算法场景描述
const CLASSIFICATION_ALGORITHM_SCENARIOS: Record<string, string> = {
  XGBoost: '通用文本分类场景，适用于客户反馈分类、情感分析、意图识别、垃圾邮件过滤等多分类任务，支持中文文本的自动分词和特征提取'
};

// Classification 算法配置 - 用于动态表单渲染
const CLASSIFICATION_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  XGBoost: {
    algorithm: 'XGBoost',
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
              defaultValue: 'f1_weighted',
              options: [
                { label: 'F1 Score (加权F1分数)', value: 'f1_weighted' },
                { label: 'F1 Macro (宏平均F1)', value: 'f1_macro' },
                { label: 'F1 Micro (微平均F1)', value: 'f1_micro' },
                { label: 'Accuracy (准确率)', value: 'accuracy' },
                { label: 'Precision Weighted (加权精确率)', value: 'precision_weighted' },
                { label: 'Recall Weighted (加权召回率)', value: 'recall_weighted' }
              ],
              tooltip: 'f1_weighted=适用于类别不平衡，f1_macro=各类别同等重要，accuracy=类别平衡时使用'
            },
            {
              name: ['hyperparams', 'use_feature_engineering'],
              label: '启用特征工程',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '是否使用特征工程增强模型效果。建议开启以获得更好的性能'
            },
            {
              name: ['hyperparams', 'random_state'],
              label: '随机种子',
              type: 'inputNumber',
              required: true,
              tooltip: '设置随机种子以确保结果可复现',
              placeholder: '例: 42',
              defaultValue: 42,
              min: 0,
              max: 2147483647,
              step: 1
            }
          ]
        },
        {
          title: '搜索空间 (Search Space)',
          subtitle: 'XGBoost 超参数搜索范围',
          fields: [
            {
              name: ['hyperparams', 'search_space', 'n_estimators'],
              label: '树的数量 (n_estimators)',
              type: 'stringArray',
              required: true,
              tooltip: '提升树的数量。更多的树可以提高性能但增加训练时间和过拟合风险',
              placeholder: '例: 50,100,200,300',
              defaultValue: '50,100,200,300'
            },
            {
              name: ['hyperparams', 'search_space', 'max_depth'],
              label: '最大树深度 (max_depth)',
              type: 'stringArray',
              required: true,
              tooltip: '树的最大深度。更深的树可以捕捉更复杂的模式，但容易过拟合',
              placeholder: '例: 3,5,7,10',
              defaultValue: '3,5,7,10'
            },
            {
              name: ['hyperparams', 'search_space', 'learning_rate'],
              label: '学习率 (learning_rate)',
              type: 'stringArray',
              required: true,
              tooltip: '每棵树的贡献权重。较小的学习率需要更多的树，但通常能获得更好的泛化性能',
              placeholder: '例: 0.01,0.05,0.1,0.2',
              defaultValue: '0.01,0.05,0.1,0.2'
            },
            {
              name: ['hyperparams', 'search_space', 'subsample'],
              label: '样本采样比例 (subsample)',
              type: 'stringArray',
              required: true,
              tooltip: '每棵树训练时随机采样的样本比例。<1.0 可以防止过拟合',
              placeholder: '例: 0.6,0.8,1.0',
              defaultValue: '0.6,0.8,1.0'
            },
            {
              name: ['hyperparams', 'search_space', 'colsample_bytree'],
              label: '特征采样比例 (colsample_bytree)',
              type: 'stringArray',
              required: true,
              tooltip: '每棵树训练时随机采样的特征比例。<1.0 可以增加模型的鲁棒性',
              placeholder: '例: 0.6,0.8,1.0',
              defaultValue: '0.6,0.8,1.0'
            },
            {
              name: ['hyperparams', 'search_space', 'min_child_weight'],
              label: '最小叶子节点权重 (min_child_weight)',
              type: 'stringArray',
              required: true,
              tooltip: '叶子节点所需的最小样本权重和。越大越保守，可以防止过拟合',
              placeholder: '例: 1,3,5',
              defaultValue: '1,3,5'
            }
          ]
        }
      ],
      preprocessing: [
        {
          title: '文本预处理 (Preprocessing)',
          subtitle: '中文文本分词和清洗配置',
          fields: [
            {
              name: ['preprocessing', 'jieba_mode'],
              label: '分词模式',
              type: 'select',
              required: true,
              placeholder: '选择结巴分词模式',
              defaultValue: 'precise',
              options: [
                { label: '精确模式 (precise)', value: 'precise' },
                { label: '全模式 (full)', value: 'full' },
                { label: '搜索引擎模式 (search)', value: 'search' }
              ],
              tooltip: 'precise=精确切分（推荐），full=扫描所有可能词汇，search=适合搜索引擎'
            },
            {
              name: ['preprocessing', 'remove_stopwords'],
              label: '移除停用词',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '移除"的"、"了"、"是"等无意义词汇，通常可以提升分类效果'
            },
            {
              name: ['preprocessing', 'remove_punctuation'],
              label: '移除标点符号',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '移除标点符号。大多数文本分类场景建议开启'
            },
            {
              name: ['preprocessing', 'custom_stopwords'],
              label: '自定义停用词',
              type: 'stringArray',
              required: false,
              tooltip: '额外的停用词列表，用逗号分隔',
              placeholder: '例: 词1,词2,词3（可选）',
              defaultValue: ''
            },
            {
              name: ['preprocessing', 'custom_dict'],
              label: '自定义词典',
              type: 'stringArray',
              required: false,
              tooltip: '业务领域的专有词汇，确保不会被错误切分',
              placeholder: '例: 机器学习,深度学习,自然语言处理（可选）',
              defaultValue: ''
            }
          ]
        }
      ],
      feature_engineering: [
        {
          title: '特征工程 (Feature Engineering)',
          subtitle: '文本特征提取配置',
          fields: [
            {
              name: ['feature_engineering', 'use_tfidf'],
              label: '启用 TF-IDF',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: 'TF-IDF（词频-逆文档频率）是经典的文本特征，通常效果良好',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            },
            {
              name: ['feature_engineering', 'use_statistical'],
              label: '启用统计特征',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '文本长度、词数等统计特征，可以作为辅助特征',
              dependencies: [['hyperparams', 'use_feature_engineering']]
            }
          ]
        },
        {
          title: 'TF-IDF 配置',
          fields: [
            {
              name: ['feature_engineering', 'tfidf', 'max_features'],
              label: '最大特征数',
              type: 'inputNumber',
              required: true,
              tooltip: '保留的最大词汇数量。过大会增加维度和训练时间，过小会损失信息',
              placeholder: '推荐: 3000-10000',
              defaultValue: 5000,
              min: 100,
              max: 50000,
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_tfidf']]
            },
            {
              name: ['feature_engineering', 'tfidf', 'min_df'],
              label: '最小文档频率',
              type: 'inputNumber',
              required: true,
              tooltip: '词汇至少在多少个文档中出现才会被保留。可以过滤罕见词',
              placeholder: '推荐: 2-5',
              defaultValue: 2,
              min: 1,
              max: 100,
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_tfidf']]
            },
            {
              name: ['feature_engineering', 'tfidf', 'max_df'],
              label: '最大文档频率',
              type: 'inputNumber',
              required: true,
              tooltip: '词汇在文档中出现频率的上限（比例）。可以过滤过于常见的词',
              placeholder: '0.0 - 1.0',
              defaultValue: 0.8,
              min: 0.1,
              max: 1.0,
              step: 0.1,
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_tfidf']]
            },
            {
              name: ['feature_engineering', 'tfidf', 'ngram_range'],
              label: 'N-gram 范围',
              type: 'stringArray',
              required: true,
              tooltip: 'N-gram 范围。[1,1]=单个词，[1,2]=单个词+双词组合',
              placeholder: '例: 1,2',
              defaultValue: '1,2',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_tfidf']]
            },
            {
              name: ['feature_engineering', 'tfidf', 'sublinear_tf'],
              label: '次线性 TF 缩放',
              type: 'switch',
              defaultValue: true,
              layout: 'horizontal',
              tooltip: '使用 log(tf) 代替 tf，可以降低高频词的影响',
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_tfidf']]
            }
          ]
        },
        {
          title: '统计特征配置',
          fields: [
            {
              name: ['feature_engineering', 'statistical_features'],
              label: '统计特征列表',
              type: 'multiSelect',
              required: true,
              placeholder: '选择需要的统计特征',
              defaultValue: ['text_length', 'word_count', 'avg_word_length', 'unique_word_ratio'],
              options: [
                { label: '文本长度 (text_length)', value: 'text_length' },
                { label: '词数 (word_count)', value: 'word_count' },
                { label: '平均词长 (avg_word_length)', value: 'avg_word_length' },
                { label: '唯一词比例 (unique_word_ratio)', value: 'unique_word_ratio' },
                { label: '标点符号数 (punctuation_count)', value: 'punctuation_count' },
                { label: '数字个数 (digit_count)', value: 'digit_count' },
                { label: '中文字符数 (chinese_char_count)', value: 'chinese_char_count' },
                { label: '英文字符数 (english_char_count)', value: 'english_char_count' }
              ],
              dependencies: [['hyperparams', 'use_feature_engineering'], ['feature_engineering', 'use_statistical']]
            }
          ]
        }
      ]
    }
  }
};

export {
  CLASSIFICATION_ALGORITHM_CONFIGS,
  CLASSIFICATION_ALGORITHM_SCENARIOS
};
