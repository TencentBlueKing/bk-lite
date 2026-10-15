/**
 * WebChat Core Library
 * Exports all core types and classes
 */

export * from './types';
export { normalizeWebChatConfig, type NormalizedWebChatConfig } from './config';
export { SessionManager } from './sessionManager';
export { StateMachine } from './stateMachine';
export { SSEHandler } from './sse';
export { SSEStreamParser } from './sseParser';
export {
  assembleAguiHistoryText,
  assembleAguiHistoryParts,
  isSilentCustomEvent,
  type HistoryContentChunk,
  type HistoryToolCall,
} from './aguiHistoryText';
export { extractMessageText } from './messageContent';
export {
  DEFAULT_LOCALE,
  createTranslator,
  getWebChatLocale,
  normalizeLocale,
  setWebChatLocale,
  translate,
  webChatCatalogs,
  type Locale,
  type Translate,
  type TranslateValues,
  type WebChatCatalog,
} from './i18n';
export * from './utils';
export * from './imeKeyboard';
export * from './platform';
export {
  CONTEXT_USAGE_EVENT,
  contextUsagePercent,
  formatContextTokens,
  parseLlmContextUsage,
  parseLlmContextUsageFromEnvelope,
  type ContextUsageSegment,
  type ContextUsageSegmentId,
  type LlmContextUsage,
} from './contextUsage';
