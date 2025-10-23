export const MODEL_TYPE_OPTIONS: Record<string, string> = {
  'deep-seek': 'DeepSeek',
  'chat-gpt': 'ChatGPT',
  'hugging_face': 'HuggingFace',
};

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

export const getConfigField = (type: string): string | undefined => {
  return CONFIG_MAP[type];
};

export const getProviderType = (type: string): string | undefined => {
  return PROVIDER_TYPE_MAP[type];
};
