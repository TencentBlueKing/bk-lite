import type { AiContextImage, AiContextProvider, AiContextSection, AiPageContext, AiPageContextPilot } from './types';
import {
  PAGE_CONTEXT_MAX_IMAGES,
  PAGE_CONTEXT_PROVIDER_TIMEOUT_MS,
  PAGE_CONTEXT_TEXT_BUDGET,
} from './types';
import { matchPilots, PAGE_CONTEXT_PILOTS } from './pilots';

export interface PageContextBridge {
  collect: () => Promise<AiPageContext | null>;
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

export const createPageContextRegistry = (options?: {
  getPathname?: () => string;
  pilots?: AiPageContextPilot[];
  timeoutMs?: number;
}) => {
  let nextId = 1;
  const providers = new Map<number, ProviderEntry>();
  const getPathname = options?.getPathname ?? (() => (typeof window === 'undefined' ? '' : window.location.pathname));
  const pilots = options?.pilots ?? PAGE_CONTEXT_PILOTS;
  const timeoutMs = options?.timeoutMs ?? PAGE_CONTEXT_PROVIDER_TIMEOUT_MS;

  const register = (provider: AiContextProvider) => {
    const id = nextId;
    nextId += 1;
    providers.set(id, { id, provider });
    return () => {
      providers.delete(id);
    };
  };

  const hasAvailable = () => providers.size > 0 || matchPilots(getPathname(), pilots).length > 0;

  const collect = async (): Promise<AiPageContext | null> => {
    const pathname = getPathname();
    const matched = matchPilots(pathname, pilots);
    const tasks: Array<Promise<Partial<AiPageContext> | null>> = [];

    for (const entry of providers.values()) {
      tasks.push(
        withTimeout(Promise.resolve().then(() => entry.provider()), timeoutMs).catch((error) => {
          console.warn('[ai-page-context] provider failed', error);
          return null;
        }),
      );
    }

    for (const pilot of matched) {
      tasks.push(
        withTimeout(
          Promise.resolve()
            .then(() => pilot.load())
            .then((mod) => mod.collect()),
          timeoutMs,
        ).catch((error) => {
          console.warn('[ai-page-context] pilot failed', error);
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

  return { register, collect, hasAvailable };
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
