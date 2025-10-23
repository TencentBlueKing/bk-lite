import { useIntl, IntlShape, PrimitiveType } from 'react-intl';
import { FormatXMLElementFn } from 'intl-messageformat';

export const useTranslation = () => {
  const intl: IntlShape = useIntl();

  interface ValuesType {
    [key: string]: PrimitiveType | FormatXMLElementFn<string, string>;
  }

  const t = (id: string, defaultMessage?: string, values?: ValuesType): string => {
    try {
      return intl.formatMessage({ id, defaultMessage }, values);
    } catch (error) {
      console.error(`Error fetching message for key "${id}":`, error);
      return defaultMessage || id;
    }
  };

  return { t };
};