import { useCallback } from 'react';
import { useIntl, IntlShape, PrimitiveType } from 'react-intl';
import { FormatXMLElementFn } from 'intl-messageformat';

interface ValuesType {
  [key: string]: PrimitiveType | FormatXMLElementFn<string, string>;
}

function formatFallback(template: string, values?: ValuesType): string {
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = values[key];
    if (value == null || typeof value === 'function') {
      return match;
    }
    return String(value);
  });
}

export const useTranslation = () => {
  const intl: IntlShape = useIntl();

  const t = useCallback((id: string, defaultMessage?: string, values?: ValuesType): string => {
    // 缺 key 时不要走 formatMessage，避免 formatjs 刷 MISSING_TRANSLATION
    if (!Object.prototype.hasOwnProperty.call(intl.messages, id)) {
      return formatFallback(defaultMessage || id, values);
    }

    try {
      const catalogMessage = intl.messages[id];
      // @formatjs/intl 在无 values 时走热路径，只用正则 `'\{(.*?)\}'` → `{$1}`，
      // 无法还原 ICU 字面量 `'{'` / `'}'`。对含这类转义的文案强制走完整格式化。
      const needsFullIcu =
        typeof catalogMessage === 'string' &&
        (catalogMessage.includes("'{'") || catalogMessage.includes("'}'"));
      return intl.formatMessage(
        { id, defaultMessage },
        needsFullIcu ? values || {} : values,
      );
    } catch (error) {
      console.error(`Error fetching message for key "${id}":`, error);
      return formatFallback(defaultMessage || id, values);
    }
  }, [intl]);

  return { t };
};
