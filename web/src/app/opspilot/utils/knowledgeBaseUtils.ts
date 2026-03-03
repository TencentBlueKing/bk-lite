import { DOCUMENT_TYPES } from '@/app/opspilot/constants/knowledge';

export const defaultIconTypes = ['zhishiku', 'zhishiku-red', 'zhishiku-blue', 'zhishiku-yellow', 'zhishiku-green'];

/**
 * 根据索引获取图标类型。
 * @param index 索引
 * @param iconTypes 图标类型数组
 * @returns 对应的图标类型
 */
export const getIconTypeByIndex = (index: number, iconTypes: string[] = defaultIconTypes): string =>
  iconTypes[index % iconTypes.length] || 'zhishiku';

export type DocumentType = typeof DOCUMENT_TYPES[keyof typeof DOCUMENT_TYPES];

/**
 * Returns the i18n key for a document source type.
 * @param type - The document type ('file', 'web_page', 'manual')
 * @returns The i18n key for the document type label
 */
export const getDocumentTypeLabelKey = (type: string): string => {
  switch (type) {
    case DOCUMENT_TYPES.FILE:
      return 'knowledge.localFile';
    case DOCUMENT_TYPES.WEB_PAGE:
      return 'knowledge.webLink';
    case DOCUMENT_TYPES.MANUAL:
      return 'knowledge.cusText';
    default:
      return type;
  }
};

/**
 * Returns the translated label for a document source type.
 * @param type - The document type ('file', 'web_page', 'manual')
 * @param t - Translation function from useTranslation hook
 * @returns The translated label for the document type
 */
export const getDocumentTypeLabel = (type: string, t: (key: string) => string): string => {
  const key = getDocumentTypeLabelKey(type);
  return key === type ? type : t(key);
};
