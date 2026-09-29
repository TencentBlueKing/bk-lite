import React, { createContext, useContext, useMemo } from 'react';
import { createTranslator, setWebChatLocale, translate, type Locale, type Translate } from '@webchat/core';

const TranslatorContext = createContext<Translate>(translate);

/**
 * 建立语言层：
 * - 每次 locale 变化同步到全局（供 imageBudget 等 React 树外的模块级文案使用）；
 * - React 树内通过 context 取词，避免逐层透传。
 */
export const WebChatLocaleProvider: React.FC<{ locale?: Locale; children: React.ReactNode }> = ({
  locale,
  children,
}) => {
  const t = useMemo(() => {
    const resolved = setWebChatLocale(locale);
    return createTranslator(resolved);
  }, [locale]);

  return <TranslatorContext.Provider value={t}>{children}</TranslatorContext.Provider>;
};

export const useTranslator = (): Translate => useContext(TranslatorContext);

/** React 树外的模块级取词（读全局 locale）。 */
export const translateOutsideTree: Translate = translate;
