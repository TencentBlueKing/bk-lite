import {
  captionFromOption,
  captureEchartsFromDom,
  captureEchartsFromDoms,
} from '@/components/chart-snapshot';

import type {
  AiContextImage,
  AiContextProvider,
  AiContextSection,
  AiPageContext,
  AiPageContextPilot,
  PageContextCollectHint,
  PageContextMessage,
  PageContextToolkit,
} from './types';
import {
  PAGE_CONTEXT_MAX_IMAGES,
  PAGE_CONTEXT_PROVIDER_TIMEOUT_MS,
  PAGE_CONTEXT_TEXT_BUDGET,
} from './types';
import { matchPilots, PAGE_CONTEXT_PILOTS } from './pilots';

export interface PageContextBridge {
  collect: (hint?: PageContextCollectHint) => Promise<AiPageContext | null>;
  hasAvailable: () => boolean;
}

declare global {
  interface Window {
    __BK_AI_PAGE_CONTEXT__?: PageContextBridge;
  }
}

interface ProviderEntry {
  id: number;
  provider: AiContextProvider;
}

interface CacheEntry {
  currentTime: string;
  content: Partial<AiPageContext>;
}

const DEFAULT_TOOLKIT: PageContextToolkit = {
  captureEchartsFromDoms,
  captureEchartsFromDom,
  captionFromOption,
};

const withTimeout = async <T>(promise: Promise<T>, ms: number): Promise<T> => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error('ai-page-context provider timeout')), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
};

const sectionPriority = (section: AiContextSection) => {
  const value = Number(section.priority);
  return Number.isFinite(value) ? value : 0;
};

export const mergePageContexts = (parts: Array<Partial<AiPageContext> | null | undefined>): AiPageContext => {
  const merged: AiPageContext = {
    url: typeof window !== 'undefined' ? window.location.href : '',
    title: typeof document !== 'undefined' ? document.title : '',
    sections: [],
    images: [],
  };
  for (const part of parts) {
    if (!part) continue;
    if (part.url) merged.url = part.url;
    if (part.app) merged.app = part.app;
    if (part.title) merged.title = part.title;
    if (part.sections?.length) merged.sections = [...(merged.sections || []), ...part.sections];
    if (part.images?.length) merged.images = [...(merged.images || []), ...part.images];
  }
  const sections = [...(merged.sections || [])].sort((a, b) => sectionPriority(b) - sectionPriority(a));
  const kept: AiContextSection[] = [];
  let used = 0;
  for (const section of sections) {
    const content = section.content || '';
    if (!content.trim()) continue;
    const remaining = PAGE_CONTEXT_TEXT_BUDGET - used;
    if (remaining <= 0) break;
    if (content.length > remaining) {
      if (used === 0) {
        kept.push({ ...section, content: content.slice(0, remaining) });
        used = PAGE_CONTEXT_TEXT_BUDGET;
      }
      continue;
    }
    kept.push(section);
    used += content.length;
  }
  const images: AiContextImage[] = [];
  for (const image of merged.images || []) {
    if (images.length >= PAGE_CONTEXT_MAX_IMAGES) break;
    if (!image?.dataUrl) continue;
    images.push(image);
  }
  return { ...merged, sections: kept, images };
};

const normalizeMessage = (raw: PageContextMessage | null | undefined): PageContextMessage | null => {
  const title = String(raw?.title || '').trim();
  if (!title) return null;
  const currentTime = raw?.currentTime == null ? undefined : String(raw.currentTime);
  return { title, currentTime };
};

export const createPageContextRegistry = (options?: {
  getPathname?: () => string;
  pilots?: AiPageContextPilot[];
  timeoutMs?: number;
  toolkit?: PageContextToolkit;
}) => {
  let nextId = 1;
  const providers = new Map<number, ProviderEntry>();
  const cache = new Map<string, CacheEntry>();
  const getPathname = options?.getPathname ?? (() => (typeof window === 'undefined' ? '' : window.location.pathname));
  const pilots = options?.pilots ?? PAGE_CONTEXT_PILOTS;
  const timeoutMs = options?.timeoutMs ?? PAGE_CONTEXT_PROVIDER_TIMEOUT_MS;
  const toolkit = options?.toolkit ?? DEFAULT_TOOLKIT;

  const register = (provider: AiContextProvider) => {
    const id = nextId;
    nextId += 1;
    providers.set(id, { id, provider });
    return () => {
      providers.delete(id);
    };
  };

  const hasAvailable = () => providers.size > 0 || matchPilots(getPathname(), pilots).length > 0;

  const collectPilot = async (
    pilot: AiPageContextPilot,
    hint?: PageContextCollectHint,
  ): Promise<Partial<AiPageContext> | null> => {
    const deadlineAt = Date.now() + timeoutMs;
    const remainingMs = () => Math.max(0, deadlineAt - Date.now());

    const mod = await withTimeout(pilot.load(), remainingMs());
    const message = normalizeMessage(
      await withTimeout(Promise.resolve().then(() => mod.getMessage()), remainingMs()),
    );
    if (!message) {
      return withTimeout(Promise.resolve().then(() => mod.getContext(toolkit, hint)), remainingMs());
    }
    const cached = cache.get(message.title);
    if (
      message.currentTime
      && cached
      && cached.currentTime === message.currentTime
    ) {
      return { ...cached.content, title: cached.content.title || message.title };
    }
    const loadFull = async () => {
      const content = await mod.getContext(toolkit, hint);
      return { ...content, title: content.title || message.title };
    };
    let next: Partial<AiPageContext>;
    let textFallback = false;
    try {
      next = await withTimeout(loadFull(), remainingMs());
    } catch (error) {
      console.warn('[ai-page-context] pilot timed out or failed', error);
      if (typeof mod.getTextContext !== 'function') {
        throw error;
      }
      const text = await Promise.resolve(mod.getTextContext());
      if (!text?.sections?.length) {
        throw error;
      }
      textFallback = true;
      next = { ...text, title: text.title || message.title };
    }
    if (message.currentTime && !textFallback) {
      cache.set(message.title, { currentTime: message.currentTime, content: next });
    } else if (!message.currentTime) {
      cache.delete(message.title);
    }
    return next;
  };

  const collect = async (hint?: PageContextCollectHint): Promise<AiPageContext | null> => {
    const pathname = getPathname();
    const matched = matchPilots(pathname, pilots);
    const tasks: Array<Promise<Partial<AiPageContext> | null>> = [];

    for (const entry of providers.values()) {
      tasks.push(
        withTimeout(Promise.resolve().then(() => entry.provider(hint)), timeoutMs).catch((error) => {
          console.debug('[ai-page-context] provider failed', error);
          return null;
        }),
      );
    }

    for (const pilot of matched) {
      tasks.push(
        collectPilot(pilot, hint).catch((error) => {
          console.debug('[ai-page-context] pilot failed', error);
          return null;
        }),
      );
    }

    if (tasks.length === 0) return null;
    const parts = await Promise.all(tasks);
    const merged = mergePageContexts(parts);
    if (!merged.sections?.length && !merged.images?.length) {
      return null;
    }
    return merged;
  };

  return { register, collect, hasAvailable, _cache: cache };
};

const singleton = createPageContextRegistry();

export const registerAiPageContext = singleton.register;
export const collectAiPageContext = singleton.collect;
export const hasAiPageContext = singleton.hasAvailable;

export const installPageContextBridge = () => {
  if (typeof window === 'undefined') return;
  window.__BK_AI_PAGE_CONTEXT__ = {
    collect: singleton.collect,
    hasAvailable: singleton.hasAvailable,
  };
};

if (typeof window !== 'undefined') {
  installPageContextBridge();
}
