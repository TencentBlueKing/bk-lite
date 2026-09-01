import type { ChartSnapshot } from '@/components/chart-snapshot/types';

export type { ChartSnapshot };

export interface AiContextSection {
  id: string;
  label: string;
  content: string;
  priority?: number;
}

/** @deprecated Prefer ChartSnapshot; kept for page_context wire format. */
export type AiContextImage = ChartSnapshot;

export interface AiPageContext {
  url?: string;
  app?: string;
  title?: string;
  sections?: AiContextSection[];
  images?: AiContextImage[];
}

export interface PageContextCollectHint {
  message?: string;
}

export interface PageContextMessage {
  title: string;
  currentTime?: string;
}

export interface PageContextToolkit {
  captureEchartsFromDoms: (
    doms: HTMLElement[],
    limit?: number,
  ) => Promise<ChartSnapshot[]>;
  captureEchartsFromDom: (limit?: number) => Promise<ChartSnapshot[]>;
  captionFromOption: (option: Record<string, unknown> | null | undefined) => string;
}

export type AiContextProvider = (
  hint?: PageContextCollectHint,
) => AiPageContext | Partial<AiPageContext> | Promise<AiPageContext | Partial<AiPageContext>>;

export interface AiPageContextPilotModule {
  getMessage: () => PageContextMessage | Promise<PageContextMessage>;
  getContext: (
    toolkit: PageContextToolkit,
    hint?: PageContextCollectHint,
  ) => Promise<Partial<AiPageContext>>;
  /** 截图超时仍可先带上 KPI / 身份等文字，避免整轮变成无页面快照。 */
  getTextContext?: () => Partial<AiPageContext> | Promise<Partial<AiPageContext>>;
}

export interface AiPageContextPilot {
  test: (pathname: string) => boolean;
  load: () => Promise<AiPageContextPilotModule>;
}

export const PAGE_CONTEXT_TEXT_BUDGET = 8000;
export const PAGE_CONTEXT_MAX_IMAGES = 6;
/** 所有页面共用的采集总 deadline；截图超时回退只发生在有 getTextContext 的 pilot，不把仪表盘 8s 套到全局。 */
export const PAGE_CONTEXT_PROVIDER_TIMEOUT_MS = 2000;
