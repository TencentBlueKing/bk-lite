import { AlgorithmConfig } from "@/app/mlops/types/task";

// Log Clustering 算法场景描述
const LOG_CLUSTERING_ALGORITHM_SCENARIOS: Record<string, string> = {
  Spell: "基于LCS的流式日志聚类算法，适用于在线日志模板提取，支持动态日志解析和异常检测场景"
};

// Log Clustering 算法配置 - 用于动态表单渲染
const LOG_CLUSTERING_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  Spell: {
    "groups": {
      "hyperparams": [
        {
          "title": "基础配置",
          "fields": [
            {
              "name": ["hyperparams", "metric"],
              "label": "优化指标",
              "type": "select",
              "required": true,
              "placeholder": "选择优化目标指标",
              "defaultValue": "template_quality_score",
              "options": [
                { "label": "模板质量评分 (template_quality_score)", "value": "template_quality_score" },
                { "label": "模板数量 (num_templates)", "value": "num_templates" },
                { "label": "覆盖率 (coverage_rate)", "value": "coverage_rate" },
                { "label": "模板多样性 (template_diversity)", "value": "template_diversity" }
              ],
              "tooltip": "template_quality_score=综合质量评分（推荐），num_templates=模板数量，coverage_rate=覆盖率，template_diversity=多样性"
            },
            {
              "name": ["hyperparams", "random_state"],
              "label": "随机种子",
              "type": "inputNumber",
              "required": true,
              "tooltip": "控制随机性，确保实验可复现。相同种子+相同参数=相同结果",
              "placeholder": "例: 42",
              "defaultValue": 42,
              "min": 0,
              "max": 2147483647,
              "step": 1
            }
          ]
        },
        {
          "title": "搜索空间 (Search Space)",
          "fields": [
            {
              "name": ["hyperparams", "search_space", "tau"],
              "label": "LCS 相似度阈值",
              "type": "stringArray",
              "required": true,
              "tooltip": "Spell LCS 相似度阈值。范围 0-1，越大越严格（生成更多模板）。0.3-0.4=宽松匹配，0.5=默认推荐，0.6-0.7=严格匹配",
              "placeholder": "例: 0.4,0.45,0.5,0.55,0.6",
              "defaultValue": "0.4,0.45,0.5,0.55,0.6"
            }
          ]
        },
        {
          "title": "",
          "subtitle": "特征工程",
          "fields": [
            {
              "name": ["hyperparams", "use_feature_engineering"],
              "label": "启用特征工程",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "Spell/Drain 等模板方法通常不需要（设为 false）；LogBERT/DeepLog 等深度学习方法建议启用（设为 true）"
            }
          ]
        }
      ],
      "preprocessing": [
        {
          "title": "日志预处理 (Preprocessing)",
          "fields": [
            {
              "name": ["preprocessing", "remove_digits"],
              "label": "替换数字",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "是否将数字替换为 <NUM>。启用可提高模板泛化能力"
            },
            {
              "name": ["preprocessing", "remove_special_chars"],
              "label": "移除特殊字符",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "是否移除特殊字符（保留字母数字和基本分隔符）"
            },
            {
              "name": ["preprocessing", "lowercase"],
              "label": "转小写",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "是否转小写。建议保持原样以保留大小写语义"
            }
          ]
        }
      ],
      "feature_engineering": [
        {
          "title": "特征工程 (Feature Engineering)",
          "subtitle": "文本特征",
          "fields": [
            {
              "name": ["feature_engineering", "text_features", "enable"],
              "label": "启用文本特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "提取文本统计特征（轻量级，计算快速）",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "text_features", "features"],
              "label": "文本特征类型",
              "type": "multiSelect",
              "required": true,
              "placeholder": "选择要提取的文本特征",
              "defaultValue": ["length", "token_count", "digit_ratio", "special_char_ratio", "uppercase_ratio", "avg_token_length"],
              "options": [
                { "label": "日志长度 (length)", "value": "length" },
                { "label": "Token数量 (token_count)", "value": "token_count" },
                { "label": "数字占比 (digit_ratio)", "value": "digit_ratio" },
                { "label": "特殊字符占比 (special_char_ratio)", "value": "special_char_ratio" },
                { "label": "大写字母占比 (uppercase_ratio)", "value": "uppercase_ratio" },
                { "label": "平均Token长度 (avg_token_length)", "value": "avg_token_length" }
              ],
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "text_features", "enable"]]
            }
          ]
        },
        {
          "title": "",
          "subtitle": "时间特征",
          "fields": [
            {
              "name": ["feature_engineering", "time_features", "enable"],
              "label": "启用时间特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "提取时间特征（需要日志数据包含时间戳列）",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "time_features", "datetime_column"],
              "label": "时间戳列名",
              "type": "input",
              "required": true,
              "placeholder": "例: timestamp",
              "defaultValue": "timestamp",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "time_features", "enable"]]
            },
            {
              "name": ["feature_engineering", "time_features", "cyclical_features"],
              "label": "周期性时间特征",
              "type": "multiSelect",
              "required": true,
              "placeholder": "选择周期性特征（会自动添加 sin/cos 编码）",
              "defaultValue": ["hour", "day_of_week"],
              "options": [
                { "label": "小时 (hour)", "value": "hour" },
                { "label": "星期 (day_of_week)", "value": "day_of_week" },
                { "label": "日期 (day)", "value": "day" },
                { "label": "月份 (month)", "value": "month" },
                { "label": "周数 (week)", "value": "week" },
                { "label": "分钟 (minute)", "value": "minute" },
                { "label": "秒 (second)", "value": "second" }
              ],
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "time_features", "enable"]]
            },
            {
              "name": ["feature_engineering", "time_features", "interval_features"],
              "label": "时间间隔特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "提取相邻日志的时间差特征",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "time_features", "enable"]]
            }
          ]
        },
        {
          "title": "",
          "subtitle": "日志级别特征",
          "fields": [
            {
              "name": ["feature_engineering", "level_features", "enable"],
              "label": "启用日志级别特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "提取日志级别特征（需要日志数据包含级别列）",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "level_features", "level_column"],
              "label": "日志级别列名",
              "type": "input",
              "required": true,
              "placeholder": "例: level",
              "defaultValue": "level",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "level_features", "enable"]]
            }
          ]
        },
        {
          "title": "",
          "subtitle": "频率特征",
          "fields": [
            {
              "name": ["feature_engineering", "frequency_features", "enable"],
              "label": "启用频率特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "提取日志出现频率和罕见度特征（轻量级）",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "frequency_features", "window_size"],
              "label": "时间窗口大小",
              "type": "input",
              "required": true,
              "placeholder": "例: 5min, 1H, 1D",
              "defaultValue": "5min",
              "tooltip": "用于计算窗口内日志频率。格式: 5min, 1H, 1D 等",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "frequency_features", "enable"]]
            }
          ]
        },
        {
          "title": "",
          "subtitle": "序列特征",
          "fields": [
            {
              "name": ["feature_engineering", "sequence_features", "enable"],
              "label": "启用序列特征",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "提取日志序列特征（中等开销，捕捉日志前后关系）",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "sequence_features", "window_size"],
              "label": "滑动窗口大小",
              "type": "inputNumber",
              "required": true,
              "placeholder": "例: 10",
              "defaultValue": 10,
              "min": 1,
              "tooltip": "用于统计窗口内的日志重复（需要保持日志时间顺序）",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "sequence_features", "enable"]]
            }
          ]
        },
        {
          "title": "",
          "subtitle": "语义特征",
          "fields": [
            {
              "name": ["feature_engineering", "semantic_features", "enable"],
              "label": "启用语义特征",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "tooltip": "提取语义特征（TF-IDF/Word2Vec/BERT），计算密集型，仅深度学习方法建议启用",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "semantic_features", "method"],
              "label": "语义特征方法",
              "type": "select",
              "required": true,
              "placeholder": "选择语义特征提取方法",
              "defaultValue": "tfidf",
              "options": [
                { "label": "TF-IDF", "value": "tfidf" },
                { "label": "Word2Vec", "value": "word2vec" },
                { "label": "BERT", "value": "bert" }
              ],
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "semantic_features", "enable"]]
            },
            {
              "name": ["feature_engineering", "semantic_features", "max_features"],
              "label": "最大特征维度",
              "type": "inputNumber",
              "required": true,
              "placeholder": "例: 100",
              "defaultValue": 100,
              "min": 10,
              "max": 1000,
              "tooltip": "TF-IDF 向量的最大维度",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "semantic_features", "enable"]]
            }
          ]
        }
      ]
    }
  }
};

export {
  LOG_CLUSTERING_ALGORITHM_CONFIGS,
  LOG_CLUSTERING_ALGORITHM_SCENARIOS
};
