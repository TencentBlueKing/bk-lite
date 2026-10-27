export type TimelineKind = 'view' | 'action' | 'error' | 'vital' | 'network' | 'console';

export interface TimelineLike {
  id: string;
  kind: TimelineKind;
  route?: string;
}

export interface TimelineRouteGroup<T extends TimelineLike> {
  view: T | null;
  vitals: T[];
  rest: T[];
}

export function groupTimelineByView<T extends TimelineLike>(items: T[]): TimelineRouteGroup<T>[] {
  const groups: TimelineRouteGroup<T>[] = [];
  for (const item of items) {
    if (item.kind === 'view' || groups.length === 0) {
      groups.push({
        view: item.kind === 'view' ? item : null,
        vitals: item.kind === 'vital' ? [item] : [],
        rest: item.kind === 'view' || item.kind === 'vital' ? [] : [item],
      });
      continue;
    }
    const current = groups[groups.length - 1];
    if (item.kind === 'vital') current.vitals.push(item);
    else current.rest.push(item);
  }
  return groups;
}
