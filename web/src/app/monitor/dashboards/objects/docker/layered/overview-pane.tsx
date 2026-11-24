'use client';

import { KpiStrip, ProInfoHint, ProSection, type KpiCardModel } from '../../host/layered/pro-chrome';
import { dockerText, type DockerCopyKey } from './copy';
import type { CollectionKind } from './reading';
import type { CountCard, DockerProView } from './view';
import { useDashboardText } from '../../../shared/utils/content-i18n';

const COLLECTION_COPY: Record<CollectionKind, DockerCopyKey> = {
  'not-connected': 'collectionNotConnected',
  unknown: 'collectionUnknown',
  expired: 'collectionExpired',
  failed: 'collectionFailed',
  success: 'collectionSuccess'
};

interface OverviewPaneProps {
  phase: 'loading' | 'ready';
  view: DockerProView | null;
  alertCount: number | null;
  alertsOpen: boolean;
  onOpenAlerts: () => void;
}

const hint = (text: string, kind: string) => <ProInfoHint kind={kind} text={text} />;

export default function DockerOverviewPane({
  phase,
  view,
  alertCount,
  alertsOpen,
  onOpenAlerts
}: OverviewPaneProps) {
  const { t } = useDashboardText();
  const text = (key: DockerCopyKey) => dockerText(t, key);
  if (phase !== 'ready' || !view) {
    const loadingItems: KpiCardModel[] = ['alerts', 'running', 'stopped', 'total', 'share'].map((key) => ({
      key,
      label: '',
      value: ''
    }));
    return (
      <ProSection title={text('sectionOverview')}>
        <div data-docker-overview="">
          <KpiStrip items={loadingItems} loading columns={loadingItems.length} />
        </div>
      </ProSection>
    );
  }
  const alertValue = alertCount == null || !Number.isFinite(alertCount)
    ? '—'
    : String(Math.max(0, Math.round(alertCount)));
  const metricSpecs: { key: string; label: DockerCopyKey; info: DockerCopyKey; card: CountCard }[] = [
    { key: 'running', label: 'kpiRunning', info: 'runningHint', card: view.running },
    { key: 'stopped', label: 'kpiStopped', info: 'stoppedHint', card: view.stopped },
    { key: 'total', label: 'kpiTotal', info: 'totalHint', card: view.total }
  ];
  const metricCards: KpiCardModel[] = metricSpecs.flatMap((item) => (
    item.card.kind === 'hidden' ? [] : [{
      key: item.key,
      label: text(item.label),
      value: item.card.text,
      info: hint(text(item.info), item.key)
    }]
  ));
  const items: KpiCardModel[] = [
    {
      key: 'docker-alerts',
      label: text('kpiAlerts'),
      value: alertValue,
      tone: alertCount != null && alertCount > 0 ? 'var(--color-fail)' : undefined,
      info: hint(text('alertHint'), 'docker-alert'),
      onActivate: onOpenAlerts,
      expanded: alertsOpen
    },
    ...metricCards,
    ...(view.share.kind === 'hidden' ? [] : [{
      key: 'share',
      label: text('kpiShare'),
      value: view.share.text,
      info: hint(`${text('shareHint')} ${text('shareEmpty')}`, 'share'),
      extra: view.share.percent == null ? undefined : (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]" data-docker-share-bar="">
          <div
            className="h-full bg-[var(--color-text-3)]"
            style={{ width: `${Math.min(100, Math.max(0, view.share.percent))}%` }}
          />
        </div>
      )
    }])
  ];

  return (
    <ProSection
      title={text('sectionOverview')}
      hint={(
        <span data-docker-collection-status={view.collection}>
          {text(COLLECTION_COPY[view.collection])}
        </span>
      )}
    >
      <div data-docker-overview="">
        <KpiStrip items={items} columns={items.length} />
      </div>
    </ProSection>
  );
}
