'use client';

import { CaretDownOutlined } from '@ant-design/icons';
import { Button, Dropdown } from 'antd';

import type { RumTraffic } from '@/app/rum/lib/degradation';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useTranslation } from '@/utils/i18n';

const SCOPES: RumTraffic[] = ['visitors', 'automated', 'all'];

/** Traffic scope selector that rewrites ?traffic= (visitors/automated/all). */
export default function TrafficScopeControl({
  onChange,
  className,
  size,
  block,
}: {
  onChange?: (scope: RumTraffic) => void;
  className?: string;
  size?: 'small' | 'middle' | 'large';
  block?: boolean;
} = {}) {
  const { t } = useTranslation();
  const { traffic, setTraffic } = useRumSearchParams();
  const current: RumTraffic =
    traffic === 'automated' || traffic === 'all' || traffic === 'bot' || traffic === 'synthetic'
      ? traffic === 'bot' || traffic === 'synthetic'
        ? 'automated'
        : traffic
      : 'visitors';

  function setScope(scope: RumTraffic) {
    setTraffic(scope);
    onChange?.(scope);
  }

  return (
    <Dropdown
      trigger={['click']}
      menu={{
        selectable: true,
        selectedKeys: [current],
        onClick: ({ key }) => setScope(key as RumTraffic),
        items: SCOPES.map((scope) => ({
          key: scope,
          label: t(`rum.traffic.${scope}`, scope),
        })),
      }}
    >
      <Button
        size={size}
        className={['inline-flex items-center gap-1', block ? 'w-full justify-between' : undefined, className]
          .filter(Boolean)
          .join(' ')}
      >
        {t(`rum.traffic.${current}`, current)}
        <CaretDownOutlined aria-hidden="true" className="text-xs text-[var(--color-text-3)]" />
      </Button>
    </Dropdown>
  );
}
