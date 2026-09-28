'use client';

import { Button } from 'antd';

import { useTranslation } from '@/utils/i18n';

import type { JsonSchema } from '../lib/types';

const BUILT_IN_SAMPLES = {
  docx: { name: 'Word', url: '/workflow-orchestration/templates/health-inspection-example.docx' },
  xlsx: { name: 'Excel', url: '/workflow-orchestration/templates/health-inspection-example.xlsx' },
} as const;

export function FileSampleLinks({ schema }: { schema: JsonSchema }) {
  const { t } = useTranslation();
  const options = schema['x-file-options'];
  const formats = options?.accept?.length ? options.accept : ['docx', 'xlsx'];
  const samples = options?.sampleFiles?.length
    ? options.sampleFiles
    : formats.map((format) => BUILT_IN_SAMPLES[format]);
  if (!samples.length) return null;

  return <div className="flex flex-wrap items-center gap-1 text-xs">
    <span className="text-[var(--color-text-3)]">{t('workflowOrchestration.launch.exampleTemplates', '示例模板：')}</span>
    {samples.map((sample) => <Button
      key={`${sample.url}:${sample.name}`}
      type="link"
      size="small"
      className="h-auto px-1"
      href={sample.url}
      download
    >
      {sample.name}
    </Button>)}
  </div>;
}
