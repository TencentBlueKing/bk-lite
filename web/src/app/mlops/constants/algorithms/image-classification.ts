import { AlgorithmConfig } from "@/app/mlops/types/task";

// Image Classification 算法场景描述
const IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS: Record<string, string> = {
  YOLOClassification: "基于 YOLO11 的高性能图片分类算法，适用于工业质检、商品分类、场景识别等多分类任务。支持多种模型规模选择（n/s/m/l/x），可根据精度和速度需求灵活配置，内置数据增强和混合精度训练加速"
};

// Image Classification 算法配置 - 用于动态表单渲染
const IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS: Record<string, AlgorithmConfig> = {
  YOLOClassification: {
    "groups": {
      "hyperparams": [
        {
          "title": "模型配置",
          "fields": [
            {
              "name": ["hyperparams", "model_name"],
              "label": "预训练模型",
              "type": "select",
              "required": true,
              "placeholder": "选择预训练模型",
              "defaultValue": "yolo11n-cls.pt",
              "tooltip": "模型规模越大，精度越高但速度越慢。n适合快速验证，m/l适合生产环境，x适合追求极致精度",
              "options": [
                { "label": "YOLOv11n (最快，适合边缘设备)", "value": "yolo11n-cls.pt" },
                { "label": "YOLOv11s (轻量级)", "value": "yolo11s-cls.pt" },
                { "label": "YOLOv11m (平衡型，推荐)", "value": "yolo11m-cls.pt" },
                { "label": "YOLOv11l (高精度)", "value": "yolo11l-cls.pt" },
                { "label": "YOLOv11x (最高精度)", "value": "yolo11x-cls.pt" }
              ]
            },
            {
              "name": ["hyperparams", "device"],
              "label": "训练设备",
              "type": "select",
              "required": true,
              "placeholder": "选择训练设备",
              "defaultValue": "auto",
              "options": [
                { "label": "自动检测 (推荐)", "value": "auto" },
                { "label": "CPU (慢但兼容性好)", "value": "cpu" },
                { "label": "GPU (单卡)", "value": "gpu" }
              ]
            }
          ]
        },
        {
          "title": "训练参数",
          "fields": [
            {
              "name": ["hyperparams", "epochs"],
              "label": "遍历轮数",
              "type": "inputNumber",
              "required": true,
              "tooltip": "完整遍历训练集的次数。小数据集建议50-100轮，大数据集100-300轮",
              "placeholder": "例: 100",
              "defaultValue": 100,
              "min": 1,
              "max": 1000
            },
            {
              "name": ["hyperparams", "lr0"],
              "label": "学习率",
              "type": "inputNumber",
              "required": true,
              "tooltip": "默认学习率。过大导致不收敛，过小导致收敛慢。推荐范围: 0.0001-0.1",
              "placeholder": "例: 0.0001,0.001,0.01,0.05,0.1",
              "defaultValue": 0.01,
              "min": 0.00001,
              "max": 1,
              "step": 0.0001
            },
            {
              "name": ["hyperparams", "batch"],
              "label": "批次大小",
              "type": "inputNumber",
              "required": true,
              "tooltip": "每批次处理的图片数量。值越大训练越快但显存占用越高。推荐 2 的幂次: 8, 16, 32, 64",
              "placeholder": "例: 8,16,32,64",
              "defaultValue": 16,
              "min": 1,
              "max": 256,
              "step": 1
            },
            {
              "name": ["hyperparams", "imgsz"],
              "label": "图片尺寸",
              "type": "inputNumber",
              "required": true,
              "tooltip": "训练时图片的统一尺寸。必须是 32 的倍数。值越大精度越高但速度越慢",
              "placeholder": "例: 224,256,320,384",
              "defaultValue": 224,
              "min": 32,
              "max": 1280,
              "step": 32
            },
            {
              "name": ["hyperparams", "optimizer"],
              "label": "优化器",
              "type": "select",
              "required": true,
              "placeholder": "选择优化器",
              "defaultValue": "AdamW",
              "tooltip": "AdamW是改进版Adam，适合大多数场景；SGD适合长时间训练",
              "options": [
                { "label": "AdamW (推荐，收敛快)", "value": "AdamW" },
                { "label": "Adam (经典优化器)", "value": "Adam" },
                { "label": "SGD (适合长训练)", "value": "SGD" },
                { "label": "RMSProp", "value": "RMSProp" }
              ]
            },
            {
              "name": ["hyperparams", "patience"],
              "label": "早停耐心值",
              "type": "inputNumber",
              "required": true,
              "tooltip": "验证集指标连续多少轮不提升则提前停止训练，避免过拟合",
              "placeholder": "例: 50",
              "defaultValue": 50,
              "min": 1,
              "max": 200
            },
            {
              "name": ["hyperparams", "amp"],
              "label": "混合精度训练",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "使用FP16+FP32混合精度，GPU训练建议开启，可加速2-3倍并节省显存"
            }
          ]
        },
        {
          "title": "超参数优化 (可选)",
          "fields": [
            {
              "name": ["hyperparams", "metric"],
              "label": "优化目标",
              "type": "select",
              "required": true,
              "placeholder": "选择优化指标",
              "defaultValue": "acc_top1",
              "options": [
                { "label": "Top-1 准确率 (推荐)", "value": "acc_top1" },
                { "label": "Top-5 准确率", "value": "acc_top5" }
              ],
              "dependencies": [["max_evals"]]
            },
            {
              "name": ["hyperparams", "search_space", "lr0"],
              "label": "学习率搜索空间",
              "type": "stringArray",
              "required": false,
              "tooltip": "可选的学习率候选值，算法会自动选择最优值",
              "placeholder": "例: 0.0001,0.001,0.01,0.05,0.1",
              "defaultValue": "0.0001,0.001,0.01,0.05,0.1",
              "dependencies": [["max_evals"]]
            },
            {
              "name": ["hyperparams", "search_space", "batch"],
              "label": "批次大小搜索空间",
              "type": "stringArray",
              "required": false,
              "tooltip": "可选的批次大小候选值",
              "placeholder": "例: 8,16,32,64",
              "defaultValue": "8,16,32,64",
              "dependencies": [["max_evals"]]
            },
            {
              "name": ["hyperparams", "search_space", "imgsz"],
              "label": "图片尺寸搜索空间",
              "type": "stringArray",
              "required": false,
              "tooltip": "可选的图片尺寸候选值",
              "placeholder": "例: 224,256,320,384",
              "defaultValue": "224,256,320,384",
              "dependencies": [["max_evals"]]
            }
          ]
        }
      ],
      "preprocessing": [
        {
          "title": "数据预处理",
          "fields": [
            {
              "name": ["preprocessing", "min_image_size"],
              "label": "最小图片尺寸",
              "type": "inputNumber",
              "required": true,
              "tooltip": "过滤掉宽或高小于此值的图片，避免低质量数据影响训练",
              "placeholder": "例: 32",
              "defaultValue": 32,
              "min": 1,
              "max": 512
            },
            {
              "name": ["preprocessing", "allowed_extensions"],
              "label": "允许的图片格式",
              "type": "multiSelect",
              "required": true,
              "placeholder": "选择支持的图片格式",
              "defaultValue": [".jpg", ".jpeg", ".png", ".bmp"],
              "options": [
                { "label": "JPG", "value": ".jpg" },
                { "label": "JPEG", "value": ".jpeg" },
                { "label": "PNG", "value": ".png" },
                { "label": "BMP", "value": ".bmp" },
                { "label": "TIFF", "value": ".tiff" },
                { "label": "WEBP", "value": ".webp" }
              ]
            }
          ]
        }
      ],
      "feature_engineering": [
        {
          "title": "数据增强",
          "fields": [
            {
              "name": ["feature_engineering", "augmentation_enabled"],
              "label": "启用数据增强",
              "type": "switch",
              "defaultValue": true,
              "layout": "horizontal",
              "tooltip": "开启后将自动应用随机翻转、旋转、缩放、亮度调整等增强，提升模型泛化能力。YOLO内部自动处理"
            }
          ]
        }
      ]
    }
  }
};

export {
  IMAGE_CLASSIFICATION_ALGORITHM_CONFIGS,
  IMAGE_CLASSIFICATION_ALGORITHM_SCENARIOS
};
