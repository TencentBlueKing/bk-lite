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
export { assembleAguiHistoryText, assembleAguiHistoryParts, isSilentCustomEvent } from './aguiHistoryText';
export { extractMessageText } from './messageContent';
export * from './utils';
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
