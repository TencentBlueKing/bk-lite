'use client';

import { Button } from 'antd';
import { useState } from 'react';

import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';

import {
  BUILTIN_SAMPLE_TEMPLATE_URLS,
  resolveBuiltinSampleTemplateUrl,
  sampleTemplateFilename,
} from '../lib/sample-templates';
import type { JsonSchema } from '../lib/types';

const BUILT_IN_SAMPLES = {
  docx: { name: 'Word', url: BUILTIN_SAMPLE_TEMPLATE_URLS.docx },
  xlsx: { name: 'Excel', url: BUILTIN_SAMPLE_TEMPLATE_URLS.xlsx },
} as const;

export function FileSampleLinks({ schema }: { schema: JsonSchema }) {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const [downloading, setDownloading] = useState<string>();
  const options = schema['x-file-options'];
  const formats = options?.accept?.length ? options.accept : ['docx', 'xlsx'];
  const samples = options?.sampleFiles?.length
    ? options.sampleFiles.map((sample) => ({ ...sample, url: resolveBuiltinSampleTemplateUrl(sample) }))
    : formats.map((format) => BUILT_IN_SAMPLES[format]);
  if (!samples.length) return null;

  return <div className="flex flex-wrap items-center gap-1 text-xs">
    <span className="text-[var(--color-text-3)]">{t('workflowOrchestration.launch.exampleTemplates', '示例模板：')}</span>
    {samples.map((sample) => <Button
      key={`${sample.url}:${sample.name}`}
      type="link"
      size="small"
      className="h-auto px-1"
      loading={downloading === sample.url}
      onClick={async () => {
        setDownloading(sample.url);
        try {
          const blob = await get<Blob>(sample.url, { responseType: 'blob' });
          const objectUrl = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = objectUrl;
          link.download = sampleTemplateFilename(sample.url);
          link.click();
          URL.revokeObjectURL(objectUrl);
        } finally {
          setDownloading(undefined);
        }
      }}
    >
      {sample.name}
    </Button>)}
  </div>;
}
