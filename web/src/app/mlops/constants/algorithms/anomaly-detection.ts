import { AlgorithmConfig } from "@/app/mlops/types/task";

// 异常检测算法场景描述
const ANOMALY_ALGORITHM_SCENARIOS: Record<string, string> = {
  ECOD: '适用于运营指标监控，可检测多维数据中的异常点，如系统资源使用率突增、业务流量异常波动等场景'
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
              min: 0,
              max: 2147483647,
              step: 1
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
            },
            {
              name: ['preprocessing', 'interpolation_limit'],
              label: '插值限制',
              type: 'inputNumber',
              required: true,
              tooltip: '连续缺失值最多插值的数量，超过此数量的连续缺失不进行插值。推荐范围: 1-100',
              placeholder: '例: 5',
              defaultValue: 5,
              min: 1,
              max: 100,
              step: 1
            },
            {
              name: ['preprocessing', 'label_column'],
              label: '标签列名',
              type: 'input',
              required: true,
              tooltip: '数据集中标签列的名称，用于区分正常和异常样本',
              placeholder: '例: label',
              defaultValue: 'label'
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

export {
  ANOMALY_ALGORITHM_CONFIGS,
  ANOMALY_ALGORITHM_SCENARIOS
};
