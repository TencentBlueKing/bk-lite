export const MODEL_TYPE_OPTIONS: Record<string, string> = {
  'deep-seek': 'DeepSeek',
  'chat-gpt': 'ChatGPT',
  'hugging_face': 'HuggingFace',
};

export const CONFIG_MAP: Record<string, string> = {
  llm_model: 'llm_config',
  embed_provider: 'embed_config',
  rerank_provider: 'rerank_config',
  ocr_provider: 'ocr_config',
};

export const getConfigField = (type: string): string | undefined => {
  return CONFIG_MAP[type];
};
