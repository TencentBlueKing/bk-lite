import { AlgorithmConfig } from "@/app/mlops/types/task";

// Timeseries Predict 算法场景描述
const TIMESERIES_ALGORITHM_SCENARIOS: Record<string, string> = {
  GradientBoosting: "短期预测，适用于有滞后特征、波动较大的时序数据",
  RandomForest: "中短期预测，适用于非线性关系、对异常值鲁棒",
  Prophet: "长期预测，适用于明显趋势和季节性（需2-3年数据）"
};

// Timeseries Predict 算法配置 - 用于动态表单渲染
const TIMESERIES_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  Prophet: {
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
              "defaultValue": "rmse",
              "options": [
                { "label": "RMSE (均方根误差)", "value": "rmse" },
                { "label": "MAE (平均绝对误差)", "value": "mae" },
                { "label": "MAPE (平均绝对百分比误差)", "value": "mape" }
              ]
            },
            {
              "name": ["hyperparams", "growth"],
              "label": "增长模式",
              "type": "select",
              "required": true,
              "tooltip": "linear=线性增长(默认)，logistic=逻辑增长(需设置容量上限)",
              "placeholder": "选择增长模式",
              "defaultValue": "linear",
              "options": [
                { "label": "线性增长 (linear)", "value": "linear" },
                { "label": "逻辑增长 (logistic)", "value": "logistic" }
              ]
            },
            {
              "name": ["hyperparams", "yearly_seasonality"],
              "label": "年度季节性",
              "type": "select",
              "required": true,
              "tooltip": "auto=自动检测（数据>=2年则启用），true=强制启用，false=禁用",
              "placeholder": "选择年度季节性",
              "defaultValue": "auto",
              "options": [
                { "label": "自动 (auto)", "value": "auto" },
                { "label": "启用 (true)", "value": "true" },
                { "label": "禁用 (false)", "value": "false" }
              ]
            },
            {
              "name": ["hyperparams", "weekly_seasonality"],
              "label": "周季节性",
              "type": "select",
              "required": true,
              "tooltip": "auto=自动检测（数据>=2周则启用），日度数据建议启用",
              "placeholder": "选择周季节性",
              "defaultValue": "auto",
              "options": [
                { "label": "自动 (auto)", "value": "auto" },
                { "label": "启用 (true)", "value": "true" },
                { "label": "禁用 (false)", "value": "false" }
              ]
            },
            {
              "name": ["hyperparams", "daily_seasonality"],
              "label": "日季节性",
              "type": "select",
              "required": true,
              "tooltip": "auto=自动检测，小时级数据建议启用，日度及以上数据建议禁用",
              "placeholder": "选择日季节性",
              "defaultValue": "auto",
              "options": [
                { "label": "自动 (auto)", "value": "auto" },
                { "label": "启用 (true)", "value": "true" },
                { "label": "禁用 (false)", "value": "false" }
              ]
            },
            {
              "name": ["hyperparams", "seasonality_prior_scale"],
              "label": "季节性强度",
              "type": "inputNumber",
              "required": true,
              "tooltip": "季节性强度的先验尺度。越大=季节性波动越灵活，越小=越平滑保守",
              "placeholder": "推荐范围: 0.01 - 10",
              "defaultValue": 10.0,
              "min": 0.01,
              "max": 100,
              "step": 0.01
            },
            {
              "name": ["hyperparams", "holidays_prior_scale"],
              "label": "节假日强度",
              "type": "inputNumber",
              "required": true,
              "tooltip": "节假日效应的先验尺度，仅在提供节假日数据时有效",
              "placeholder": "推荐范围: 0.01 - 10",
              "defaultValue": 10.0,
              "min": 0.01,
              "max": 100,
              "step": 0.01
            },
            {
              "name": ["hyperparams", "n_changepoints"],
              "label": "变点数量",
              "type": "inputNumber",
              "required": true,
              "tooltip": "Prophet 自动在训练数据前 80% 均匀分布的潜在趋势变点数量",
              "placeholder": "推荐: 10-50",
              "defaultValue": 25,
              "min": 1,
              "max": 200
            }
          ]
        },
        {
          "title": "搜索空间 (Search Space)",
          "fields": [
            {
              "name": ["hyperparams", "search_space", "seasonality_mode"],
              "label": "季节性模式",
              "type": "stringArray",
              "required": true,
              "tooltip": "additive=加性(趋势+季节性，波动固定)，multiplicative=乘性(趋势×季节性，波动随趋势变化)",
              "placeholder": "例: additive,multiplicative",
              "defaultValue": "additive,multiplicative"
            },
            {
              "name": ["hyperparams", "search_space", "changepoint_prior_scale"],
              "label": "变点灵活性",
              "type": "stringArray",
              "required": true,
              "tooltip": "最重要的超参数！控制趋势变化灵活度。大值(0.5)=灵活但易过拟合，小值(0.001)=平滑但可能欠拟合",
              "placeholder": "例: 0.001,0.01,0.05,0.1,0.5",
              "defaultValue": "0.001,0.01,0.05,0.1,0.5"
            },
            {
              "name": ["hyperparams", "search_space", "seasonality_prior_scale"],
              "label": "季节性强度搜索",
              "type": "stringArray",
              "required": true,
              "tooltip": "搜索最优的季节性强度（会覆盖上面的固定值）",
              "placeholder": "例: 0.01,0.1,1.0,10.0",
              "defaultValue": "0.01,0.1,1.0,10.0"
            },
            {
              "name": ["hyperparams", "search_space", "holidays_prior_scale"],
              "label": "节假日强度搜索",
              "type": "stringArray",
              "required": true,
              "tooltip": "搜索最优的节假日效应强度",
              "placeholder": "例: 0.01,0.1,1.0,10.0",
              "defaultValue": "0.01,0.1,1.0,10.0"
            },
            {
              "name": ["hyperparams", "search_space", "n_changepoints"],
              "label": "变点数量搜索",
              "type": "stringArray",
              "required": true,
              "tooltip": "搜索最优的变点数量（会覆盖上面的固定值）",
              "placeholder": "例: 10,25,50,100",
              "defaultValue": "10,25,50,100"
            }
          ]
        }
      ],
      "preprocessing": [
        {
          "title": "数据预处理 (Preprocessing)",
          "fields": [
            {
              "name": ["preprocessing", "handle_missing"],
              "label": "缺失值处理",
              "type": "select",
              "required": true,
              "placeholder": "选择缺失值处理方式",
              "defaultValue": "interpolate",
              "options": [
                { "label": "线性插值 (interpolate)", "value": "interpolate" },
                { "label": "前向填充 (ffill)", "value": "ffill" },
                { "label": "后向填充 (bfill)", "value": "bfill" },
                { "label": "删除 (drop)", "value": "drop" },
                { "label": "中位数填充 (median)", "value": "median" }
              ]
            },
            {
              "name": ["preprocessing", "max_missing_ratio"],
              "label": "最大缺失率",
              "type": "inputNumber",
              "required": true,
              "placeholder": "0.0 - 1.0",
              "defaultValue": 0.3,
              "min": 0,
              "max": 1,
              "step": 0.1
            },
            {
              "name": ["preprocessing", "interpolation_limit"],
              "label": "插值限制",
              "type": "inputNumber",
              "required": true,
              "placeholder": "最多填充的连续缺失点数",
              "defaultValue": 3,
              "min": 1
            }
          ]
        }
      ]
    }
  },
  GradientBoosting: {
    "groups": {
      "hyperparams": [
        {
          "title": "训练配置",
          "fields": [
            {
              "name": ["hyperparams", "metric"],
              "label": "优化指标",
              "type": "select",
              "required": true,
              "placeholder": "选择优化目标指标",
              "defaultValue": "rmse",
              "options": [
                { "label": "RMSE (均方根误差)", "value": "rmse" },
                { "label": "MAE (平均绝对误差)", "value": "mae" },
                { "label": "MAPE (平均绝对百分比误差)", "value": "mape" }
              ]
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
          "subtitle": "树结构参数",
          "fields": [
            {
              "name": ["hyperparams", "search_space", "n_estimators"],
              "label": "树的数量",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 50,100,200,300",
              "defaultValue": "50,100,200,300"
            },
            {
              "name": ["hyperparams", "search_space", "max_depth"],
              "label": "树最大深度",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 3,5,7,10",
              "defaultValue": "3,5,7,10"
            },
            {
              "name": ["hyperparams", "search_space", "learning_rate"],
              "label": "学习率",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 0.01,0.05,0.1,0.2",
              "defaultValue": "0.01,0.05,0.1,0.2"
            }
          ]
        },
        {
          "title": "",
          "subtitle": "采样控制参数",
          "fields": [
            {
              "name": ["hyperparams", "search_space", "min_samples_split"],
              "label": "最小分裂样本数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 2,5,10",
              "defaultValue": "2,5,10"
            },
            {
              "name": ["hyperparams", "search_space", "min_samples_leaf"],
              "label": "叶节点最小样本数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1,2,4",
              "defaultValue": "1,2,4"
            },
            {
              "name": ["hyperparams", "search_space", "subsample"],
              "label": "子采样比例",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 0.7,0.8,0.9,1.0",
              "defaultValue": "0.7,0.8,0.9,1.0"
            }
          ]
        },
        {
          "title": "",
          "subtitle": "特征参数",
          "fields": [
            {
              "name": ["hyperparams", "use_feature_engineering"],
              "label": "启用特征工程",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "启用完整特征工程（滚动窗口、时间特征等）或仅使用简单滞后特征"
            },
            {
              "name": ["hyperparams", "search_space", "lag_features"],
              "label": "滞后特征数量",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 6,12,24",
              "defaultValue": "6,12,24",
              "tooltip": "仅在 use_feature_engineering=false 时使用"
            }
          ]
        }
      ],
      "preprocessing": [
        {
          "title": "数据预处理 (Preprocessing)",
          "fields": [
            {
              "name": ["preprocessing", "handle_missing"],
              "label": "缺失值处理",
              "type": "select",
              "required": true,
              "placeholder": "选择缺失值处理方式",
              "defaultValue": "interpolate",
              "options": [
                { "label": "线性插值 (interpolate)", "value": "interpolate" },
                { "label": "前向填充 (ffill)", "value": "ffill" },
                { "label": "后向填充 (bfill)", "value": "bfill" },
                { "label": "删除 (drop)", "value": "drop" },
                { "label": "中位数填充 (median)", "value": "median" }
              ]
            },
            {
              "name": ["preprocessing", "max_missing_ratio"],
              "label": "最大缺失率",
              "type": "inputNumber",
              "required": true,
              "placeholder": "0.0 - 1.0",
              "defaultValue": 0.3,
              "min": 0,
              "max": 1,
              "step": 0.1
            },
            {
              "name": ["preprocessing", "interpolation_limit"],
              "label": "插值限制",
              "type": "inputNumber",
              "required": true,
              "placeholder": "最多填充的连续缺失点数",
              "defaultValue": 3,
              "min": 1
            }
          ]
        }
      ],
      "feature_engineering": [
        {
          "title": "特征工程 (Feature Engineering)",
          "fields": [
            {
              "name": ["feature_engineering", "lag_periods"],
              "label": "滞后期",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1,2,3,7,14",
              "defaultValue": "1,2,3,7,14",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "rolling_windows"],
              "label": "滚动窗口大小",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 7,14,30",
              "defaultValue": "7,14,30",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "rolling_features"],
              "label": "滚动窗口统计",
              "type": "multiSelect",
              "required": true,
              "placeholder": "选择统计函数",
              "defaultValue": ["mean", "std", "min", "max"],
              "options": [
                { "label": "均值 (mean)", "value": "mean" },
                { "label": "标准差 (std)", "value": "std" },
                { "label": "最小值 ('min')", "value": "min" },
                { "label": "最大值 ('max')", "value": "max" },
                { "label": "中位数 (median)", "value": "median" },
                { "label": "求和 (sum)", "value": "sum" }
              ],
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_temporal_features"],
              "label": "时间特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_cyclical_features"],
              "label": "周期性编码",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_diff_features"],
              "label": "差分特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "diff_periods"],
              "label": "差分期数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1",
              "defaultValue": "1",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "use_diff_features"]]
            }
          ]
        }
      ]
    }
  },
  RandomForest: {
    "groups": {
      "hyperparams": [
        {
          "title": "训练配置",
          "fields": [
            {
              "name": ["hyperparams", "metric"],
              "label": "优化指标",
              "type": "select",
              "required": true,
              "placeholder": "选择优化目标指标",
              "defaultValue": "rmse",
              "options": [
                { "label": "RMSE (均方根误差)", "value": "rmse" },
                { "label": "MAE (平均绝对误差)", "value": "mae" },
                { "label": "MAPE (平均绝对百分比误差)", "value": "mape" }
              ]
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
          "subtitle": "树结构参数",
          "fields": [
            {
              "name": ["hyperparams", "search_space", "n_estimators"],
              "label": "树的数量",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 50,100,200,300",
              "defaultValue": "50,100,200,300"
            },
            {
              "name": ["hyperparams", "search_space", "max_depth"],
              "label": "树最大深度",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 3,5,7,10",
              "defaultValue": "3,5,7,10"
            },
            {
              "name": ["hyperparams", "search_space", "min_samples_split"],
              "label": "最小分裂样本数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 2,5,10",
              "defaultValue": "2,5,10"
            },
            {
              "name": ["hyperparams", "search_space", "min_samples_leaf"],
              "label": "叶节点最小样本数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1,2,4",
              "defaultValue": "1,2,4"
            },
            {
              "name": ["hyperparams", "search_space", "max_features"],
              "label": "最大特征数",
              "type": "stringArray",
              "required": true,
              "tooltip": "sqrt=特征数的平方根(推荐)，log2=特征数的对数(更保守)",
              "placeholder": "例: sqrt,log2",
              "defaultValue": "sqrt,log2"
            }
          ]
        },
        {
          "title": "",
          "subtitle": "特征参数",
          "fields": [
            {
              "name": ["hyperparams", "use_feature_engineering"],
              "label": "启用特征工程",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "启用完整特征工程（滚动窗口、时间特征等）或仅使用简单滞后特征"
            },
            {
              "name": ["hyperparams", "search_space", "lag_features"],
              "label": "滞后特征数量",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 6,12,24",
              "defaultValue": "6,12,24",
              "tooltip": "仅在 use_feature_engineering=false 时使用"
            }
          ]
        }
      ],
      "preprocessing": [
        {
          "title": "数据预处理 (Preprocessing)",
          "fields": [
            {
              "name": ["preprocessing", "handle_missing"],
              "label": "缺失值处理",
              "type": "select",
              "required": true,
              "placeholder": "选择缺失值处理方式",
              "defaultValue": "interpolate",
              "options": [
                { "label": "线性插值 (interpolate)", "value": "interpolate" },
                { "label": "前向填充 (ffill)", "value": "ffill" },
                { "label": "后向填充 (bfill)", "value": "bfill" },
                { "label": "删除 (drop)", "value": "drop" },
                { "label": "中位数填充 (median)", "value": "median" }
              ]
            },
            {
              "name": ["preprocessing", "max_missing_ratio"],
              "label": "最大缺失率",
              "type": "inputNumber",
              "required": true,
              "placeholder": "0.0 - 1.0",
              "defaultValue": 0.3,
              "min": 0,
              "max": 1,
              "step": 0.1
            },
            {
              "name": ["preprocessing", "interpolation_limit"],
              "label": "插值限制",
              "type": "inputNumber",
              "required": true,
              "placeholder": "最多填充的连续缺失点数",
              "defaultValue": 3,
              "min": 1
            }
          ]
        }
      ],
      "feature_engineering": [
        {
          "title": "特征工程 (Feature Engineering)",
          "fields": [
            {
              "name": ["feature_engineering", "lag_periods"],
              "label": "滞后期",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1,2,3,7,14",
              "defaultValue": "1,2,3,7,14",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "rolling_windows"],
              "label": "滚动窗口大小",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 7,14,30",
              "defaultValue": "7,14,30",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "rolling_features"],
              "label": "滚动窗口统计",
              "type": "multiSelect",
              "required": true,
              "placeholder": "选择统计函数",
              "defaultValue": ["mean", "std", "min", "max"],
              "options": [
                { "label": "均值 (mean)", "value": "mean" },
                { "label": "标准差 (std)", "value": "std" },
                { "label": "最小值 ('min')", "value": "min" },
                { "label": "最大值 ('max')", "value": "max" },
                { "label": "中位数 (median)", "value": "median" },
                { "label": "求和 (sum)", "value": "sum" }
              ],
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_temporal_features"],
              "label": "时间特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_cyclical_features"],
              "label": "周期性编码",
              "type": "switch",
              "defaultValue": false,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "use_diff_features"],
              "label": "差分特征",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "dependencies": [["hyperparams", "use_feature_engineering"]]
            },
            {
              "name": ["feature_engineering", "diff_periods"],
              "label": "差分期数",
              "type": "stringArray",
              "required": true,
              "placeholder": "例: 1",
              "defaultValue": "1",
              "dependencies": [["hyperparams", "use_feature_engineering"], ["feature_engineering", "use_diff_features"]]
            }
          ]
        }
      ]
    }
  }
};

export {
  TIMESERIES_ALGORITHM_CONFIGS,
  TIMESERIES_ALGORITHM_SCENARIOS
};
