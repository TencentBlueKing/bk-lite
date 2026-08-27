'use client';

import ServiceLanguageIcon, { hasKnownServiceLanguage } from '@/app/apm/components/service-language-icon';
import { resolveTopologyObjectIcon } from '@/app/apm/components/topology-object-icon';

export default function TopologyServiceIcon({
  kind,
  language,
  inferredSystem,
  serviceName,
  size = 16,
  x,
  y,
}: {
  kind?: string;
  language?: string;
  inferredSystem?: string;
  serviceName?: string;
  size?: number;
  x?: number;
  y?: number;
}) {
  if (kind !== 'inferred' && hasKnownServiceLanguage(language)) {
    return <ServiceLanguageIcon language={language} size={size} x={x} y={y} />;
  }
  const icon = resolveTopologyObjectIcon(inferredSystem, serviceName);
  return (
    <image
      aria-hidden="true"
      data-service-icon={icon.kind}
      height={size}
      href={`/assets/icons/${icon.file}.svg`}
      width={size}
      x={x}
      y={y}
    />
  );
}
