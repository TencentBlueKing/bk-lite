export type {
  AiContextImage,
  AiContextProvider,
  AiContextSection,
  AiPageContext,
  AiPageContextPilot,
  AiPageContextPilotModule,
  PageContextCollectHint,
  PageContextMessage,
  PageContextToolkit,
} from './types';
export {
  PAGE_CONTEXT_MAX_IMAGES,
  PAGE_CONTEXT_PROVIDER_TIMEOUT_MS,
  PAGE_CONTEXT_TEXT_BUDGET,
} from './types';
export {
  collectAiPageContext,
  createPageContextRegistry,
  hasAiPageContext,
  installPageContextBridge,
  mergePageContexts,
  registerAiPageContext,
} from './registry';
export { matchPilots, registerPageContextPilot } from './pilots';
export {
  captionFromOption,
  captureEchartsFromDom,
  captureEchartsFromDoms,
} from '@/components/chart-snapshot';
export { useAiPageContext } from './useAiPageContext';
