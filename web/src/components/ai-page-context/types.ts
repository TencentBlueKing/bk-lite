export interface AiContextSection {
  id: string;
  label: string;
  content: string;
  priority?: number;
}

export interface AiContextImage {
  caption?: string;
  dataUrl: string;
}

export interface AiPageContext {
  url?: string;
  app?: string;
  title?: string;
  sections?: AiContextSection[];
  images?: AiContextImage[];
}

export type AiContextProvider = () => AiPageContext | Partial<AiPageContext> | Promise<AiPageContext | Partial<AiPageContext>>;

export interface AiPageContextPilot {
  test: (pathname: string) => boolean;
  load: () => Promise<{ collect: () => Promise<Partial<AiPageContext>> }>;
}

export const PAGE_CONTEXT_TEXT_BUDGET = 8000;
export const PAGE_CONTEXT_MAX_IMAGES = 6;
export const PAGE_CONTEXT_PROVIDER_TIMEOUT_MS = 2000;
