'use client';

import { Tooltip } from 'antd';
import ServiceLanguageIcon, { serviceLanguageLabel } from '@/app/apm/components/service-language-icon';
import { useTranslation } from '@/utils/i18n';

export default function ServiceLanguage({
  language,
  size = 16,
}: {
  language?: string;
  size?: number;
}) {
  const { t } = useTranslation();
  const normalized = language?.trim() ?? '';
  const label = serviceLanguageLabel(language, t('apm.language.unknown', '未知'));
  const title = normalized
    ? t('apm.language.tooltip', 'OpenTelemetry SDK 语言：{label}', { label })
    : t('apm.language.missing', '暂未观测到 SDK 语言');
  return (
    <Tooltip title={title}>
      <span
        aria-label={title}
        className="inline-flex shrink-0 text-[var(--color-text-3)]"
        role="img"
      >
        <ServiceLanguageIcon language={language} size={size} />
      </span>
    </Tooltip>
  );
}
