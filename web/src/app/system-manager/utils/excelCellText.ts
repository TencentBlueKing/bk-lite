const MAILTO_PREFIX = /^mailto:/i;

function asTrimmedText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim();
  }
  return '';
}

function stripMailto(value: string): string {
  return value.replace(MAILTO_PREFIX, '').split('?')[0].trim();
}

/**
 * ExcelJS 把超链接、公式、富文本存成对象。直接 String() 会得到 [object Object]，
 * 邮箱列在 Excel 里尤其容易被自动做成 mailto 超链接。
 */
export function excelCellToText(value: unknown): string {
  const primitive = asTrimmedText(value);
  if (primitive) return primitive;
  if (!value || typeof value !== 'object') return '';

  const cell = value as {
    text?: unknown;
    result?: unknown;
    hyperlink?: unknown;
    richText?: Array<{ text?: unknown }>;
  };

  const fromText = asTrimmedText(cell.text);
  if (fromText) return stripMailto(fromText);

  const fromResult = asTrimmedText(cell.result);
  if (fromResult) return fromResult;

  if (Array.isArray(cell.richText)) {
    const richText = cell.richText.map((part) => asTrimmedText(part?.text)).join('');
    if (richText) return richText;
  }

  const fromLink = asTrimmedText(cell.hyperlink);
  if (fromLink) return stripMailto(fromLink);

  return '';
}
