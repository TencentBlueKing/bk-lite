export const CLIENT_MODULES_MAP = {
  opspilot: ['bot', 'skill', 'knowledge', 'tools', 'provider']
}

// Constants definition
export const SUB_MODULE_MAP: { [key: string]: string[] } = {
  provider: ['llm_model', 'embed_model', 'rerank_model', 'ocr_model']
};

export const EDITABLE_MODULES = ['bot', 'llm_model', 'embed_model', 'rerank_model', 'ocr_model'];
