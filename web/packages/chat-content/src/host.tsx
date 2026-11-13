"use client";
import React, {
  createContext,
  useContext,
  useCallback,
  type ReactNode,
} from "react";
import zh from "./zh.json";
import en from "./en.json";
import type { WikiCitation } from "./types";

export type Translate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => string;
export interface ChatContentHost {
  locale?: string;
  translate?: Translate;
  post?: <T>(path: string, body: unknown) => Promise<T>;
  loadCitation?: (citation: WikiCitation) => Promise<string>;
  submitApproval?: (body: Record<string, unknown>) => Promise<void>;
}
const HostContext = createContext<ChatContentHost>({});
export function ChatContentProvider({
  value,
  children,
}: {
  value: ChatContentHost;
  children?: ReactNode;
}): React.JSX.Element {
  return <HostContext.Provider value={value}>{children}</HostContext.Provider>;
}
export function useChatContentHost() {
  return useContext(HostContext);
}
export function useTranslation() {
  const host = useChatContentHost();
  const t: Translate = useCallback(
    (key, fallback, values) => {
      const catalog: Record<string, string> = host.locale === "en" ? en : zh;
      const text =
        host.translate?.(key, catalog[key] ?? fallback, values) ??
        catalog[key] ??
        fallback ??
        key;
      return text.replace(/\{(\w+)\}/g, (match, name) =>
        values?.[name] == null ? match : String(values[name]),
      );
    },
    [host.translate, host.locale],
  );
  return { t };
}
export default function useApiClient() {
  const host = useChatContentHost();
  return {
    post:
      host.post ??
      (async () => {
        throw new Error("当前入口不支持此操作");
      }),
  };
}
export function isSilentRequestError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
