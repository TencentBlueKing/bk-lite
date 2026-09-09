import type { LatestRequestGuard } from '@/context/latestRequestGuard';
import type { ApmAlertEvent, ApmEventSnapshot, ApmNotificationDelivery } from '@/app/apm/types';

export interface AlertEventRequestKey {
  alertId: string;
  eventId: string;
}

export function pickAlertEventEvidence(
  snapshots: ApmEventSnapshot[],
  eventId: string,
): ApmEventSnapshot | null {
  return snapshots.find((item) => item.event_id === eventId) ?? null;
}

export function commitAlertEventEvidenceSuccess(
  guard: LatestRequestGuard,
  requestId: number,
  requested: AlertEventRequestKey,
  snapshots: ApmEventSnapshot[],
  deliveries: ApmNotificationDelivery[],
  apply: (evidence: ApmEventSnapshot | null, deliveries: ApmNotificationDelivery[]) => void,
): boolean {
  return guard.commitIfCurrent(requestId, () => {
    const evidence = pickAlertEventEvidence(snapshots, requested.eventId);
    const scopedDeliveries = deliveries.filter(
      (item) => !item.event_id || item.event_id === requested.eventId,
    );
    apply(evidence, scopedDeliveries);
  });
}

export function commitAlertEventEvidenceSettled(
  guard: LatestRequestGuard,
  requestId: number,
  settle: () => void,
): boolean {
  return guard.commitIfCurrent(requestId, settle);
}

export function canRetryAlertEventDelivery(
  delivery: ApmNotificationDelivery | undefined,
  selectedEvent: Pick<ApmAlertEvent, 'event_id'> | null,
): delivery is ApmNotificationDelivery {
  return Boolean(
    delivery
    && selectedEvent?.event_id
    && delivery.event_id
    && delivery.event_id === selectedEvent.event_id,
  );
}
