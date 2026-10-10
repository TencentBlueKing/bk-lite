export const BUILTIN_SAMPLE_TEMPLATE_URLS = {
  docx: '/workflow_orchestration/api/workflows/sample-templates/docx/',
  xlsx: '/workflow_orchestration/api/workflows/sample-templates/xlsx/',
} as const;

export type BuiltinSampleTemplateFormat = keyof typeof BUILTIN_SAMPLE_TEMPLATE_URLS;

export function resolveBuiltinSampleTemplateUrl(sample: { name: string; url: string }): string {
  const url = String(sample.url || '');
  if (url.includes('/sample-templates/docx')) return BUILTIN_SAMPLE_TEMPLATE_URLS.docx;
  if (url.includes('/sample-templates/xlsx')) return BUILTIN_SAMPLE_TEMPLATE_URLS.xlsx;
  if (url.endsWith('.docx') || /word/i.test(sample.name)) return BUILTIN_SAMPLE_TEMPLATE_URLS.docx;
  if (url.endsWith('.xlsx') || /excel/i.test(sample.name)) return BUILTIN_SAMPLE_TEMPLATE_URLS.xlsx;
  return url;
}

export function sampleTemplateFilename(url: string): string {
  if (url.includes('/docx')) return 'health-inspection-example.docx';
  if (url.includes('/xlsx')) return 'health-inspection-example.xlsx';
  return url.split('/').filter(Boolean).pop() || 'sample-template';
}
