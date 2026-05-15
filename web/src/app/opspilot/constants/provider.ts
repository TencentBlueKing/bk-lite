export const MODEL_TYPE_OPTIONS: Record<string, string> = {
  'deep-seek': 'DeepSeek',
  'chat-gpt': 'ChatGPT',
  'hugging_face': 'HuggingFace',
};

import type {ProtocolType, ProviderResourceType, VendorType} from '@/app/opspilot/types/provider';

export const MODEL_CATEGORY_OPTIONS = [
  { value: 'text', label: '文本类' },
  { value: 'multimodal', label: '多模态' },
  { value: 'reasoning', label: '推理增强' },
  { value: 'code', label: '代码类' },
  { value: 'other', label: '其他' }
];

export const MODEL_CATEGORY_MAPPING: Record<string, string> = MODEL_CATEGORY_OPTIONS.reduce(
  (acc, option) => {
    acc[option.value] = option.label;
    return acc;
  },
  {} as Record<string, string>
);

export const CONFIG_MAP: Record<string, string> = {
  llm_model: 'llm_config',
  embed_provider: 'embed_config',
  rerank_provider: 'rerank_config',
  ocr_provider: 'ocr_config',
};

export const PROVIDER_TYPE_MAP: Record<string, string> = {
  llm_model: 'llm',
  embed_provider: 'embed',
  rerank_provider: 'rerank',
  ocr_provider: 'ocr',
};

export const MODEL_TABS: Array<{ key: string; label: string; type: ProviderResourceType }> = [
  { key: '1', label: 'LLM Model', type: 'llm_model' },
  { key: '2', label: 'Embed Model', type: 'embed_provider' },
  { key: '3', label: 'Rerank Model', type: 'rerank_provider' },
  { key: '4', label: 'OCR Model', type: 'ocr_provider' },
];

export const VENDOR_OPTIONS: Array<{
  value: VendorType;
  label: string;
  icon: string;
  defaultApiBase: string;
}> = [
  { value: 'openai', label: 'OpenAI', icon: 'GPT', defaultApiBase: 'https://api.openai.com/v1' },
  { value: 'azure', label: 'Azure', icon: 'azure', defaultApiBase: 'https://{resource}.openai.azure.com/' },
  { value: 'aliyun', label: '阿里云', icon: 'Alibaba', defaultApiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { value: 'zhipu', label: '智谱', icon: 'Zhipu', defaultApiBase: 'https://open.bigmodel.cn/api/paas/v4' },
  { value: 'baidu', label: '百度', icon: 'Baidu', defaultApiBase: 'https://qianfan.baidubce.com/v2' },
  { value: 'anthropic', label: 'Anthropic', icon: 'Anthropic', defaultApiBase: 'https://api.anthropic.com' },
  { value: 'deepseek', label: 'DeepSeek', icon: 'DeepSeek', defaultApiBase: 'https://api.deepseek.com/v1' },
  { value: 'other', label: '其他', icon: 'Default', defaultApiBase: '' },
];

export const VENDOR_LABEL_MAP: Record<VendorType, string> = VENDOR_OPTIONS.reduce((acc, option) => {
  acc[option.value] = option.label;
  return acc;
}, {} as Record<VendorType, string>);

export const VENDOR_ICON_MAP: Record<VendorType, string> = VENDOR_OPTIONS.reduce((acc, option) => {
  acc[option.value] = option.icon;
  return acc;
}, {} as Record<VendorType, string>);

export const getVendorOption = (vendorType: VendorType) => {
  return VENDOR_OPTIONS.find((option) => option.value === vendorType);
};

export const getConfigField = (type: string): string | undefined => {
  return CONFIG_MAP[type];
};

export const getProviderType = (type: ProviderResourceType): string | undefined => {
  return PROVIDER_TYPE_MAP[type];
};

// 协议类型选项
export const PROTOCOL_TYPE_OPTIONS: Array<{
  value: ProtocolType;
  label: string;
  defaultApiBase: string;
}> = [
  { value: 'openai', label: 'OpenAI 协议', defaultApiBase: '' },
  { value: 'anthropic', label: 'Anthropic 协议', defaultApiBase: 'https://api.anthropic.com' },
];

// 获取供应商类型对应的默认 Anthropic API 地址
export const getAnthropicApiBase = (vendorType: VendorType): string => {
  if (vendorType === 'deepseek') {
    return 'https://api.deepseek.com/anthropic';
  }
  return 'https://api.anthropic.com';
};

// 获取供应商类型对应的默认协议
export const getDefaultProtocolType = (vendorType: VendorType): ProtocolType => {
  if (vendorType === 'anthropic') {
    return 'anthropic';
  }
  return 'openai';
};

// 判断供应商类型是否支持协议选择（deepseek 和 other 类型支持）
export const supportsProtocolSelection = (vendorType: VendorType): boolean => {
  return vendorType === 'deepseek' || vendorType === 'other';
};
