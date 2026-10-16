export interface FilterOptionLabelSnapshot {
  coveredIds: ReadonlySet<string>;
  labelsByFilterId: Record<string, Record<string, string> | undefined>;
  /** 该筛选已发布的标签被清掉的次数。没有标签时不增加。 */
  revisions: Readonly<Record<string, number>>;
}

export interface FilterOptionLabelStore {
  claim: (ids: string[]) => () => void;
  publish: (filterId: string, labels: Record<string, string>) => void;
  /**
   * 删掉已经发布的标签，并只递增这些 id 的 revision。
   * 从未发布过的 id 不动。`null` 表示处理全部已发布标签。空数组不做事。
   */
  invalidate: (filterIds: readonly string[] | null) => void;
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => FilterOptionLabelSnapshot;
  getServerSnapshot: () => FilterOptionLabelSnapshot;
}

const sameLabelMap = (
  left: Record<string, string> | undefined,
  right: Record<string, string> | undefined,
) => {
  if (left === right) return true;
  if (!left || !right) return false;
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  return leftKeys.every((key) => left[key] === right[key]);
};

const snapshotOf = (
  coveredIds: ReadonlySet<string>,
  labelsByFilterId: Record<string, Record<string, string> | undefined>,
  revisions: Readonly<Record<string, number>>,
): FilterOptionLabelSnapshot => ({ coveredIds, labelsByFilterId, revisions });

/** 一块画布上的动态选项标签。筛选栏和标题解析共用，避免同一筛选再拉一次数据源。 */
export const createFilterOptionLabelStore = (): FilterOptionLabelStore => {
  const coveredCounts = new Map<string, number>();
  let labelsByFilterId: Record<string, Record<string, string> | undefined> = {};
  let revisions: Record<string, number> = {};
  let snapshot = snapshotOf(new Set<string>(), labelsByFilterId, revisions);
  const serverSnapshot = snapshot;
  const listeners = new Set<() => void>();

  const emit = (coveredIds: Set<string>) => {
    snapshot = snapshotOf(coveredIds, labelsByFilterId, revisions);
    listeners.forEach((listener) => listener());
  };

  return {
    claim: (ids) => {
      const unique = [...new Set(ids.filter(Boolean))];
      let changed = false;
      unique.forEach((id) => {
        const next = (coveredCounts.get(id) ?? 0) + 1;
        if (next === 1) changed = true;
        coveredCounts.set(id, next);
      });
      if (changed) emit(new Set(coveredCounts.keys()));
      return () => {
        let released = false;
        unique.forEach((id) => {
          const next = (coveredCounts.get(id) ?? 1) - 1;
          if (next <= 0) {
            coveredCounts.delete(id);
            released = true;
            return;
          }
          coveredCounts.set(id, next);
        });
        if (released) emit(new Set(coveredCounts.keys()));
      };
    },
    invalidate: (filterIds) => {
      if (filterIds && filterIds.length === 0) return;
      const ids = (filterIds ?? Object.keys(labelsByFilterId)).filter((id) => (
        Object.prototype.hasOwnProperty.call(labelsByFilterId, id)
      ));
      if (ids.length === 0) return;
      const nextLabels = { ...labelsByFilterId };
      const nextRevisions = { ...revisions };
      ids.forEach((id) => {
        delete nextLabels[id];
        nextRevisions[id] = (nextRevisions[id] ?? 0) + 1;
      });
      labelsByFilterId = nextLabels;
      revisions = nextRevisions;
      emit(new Set(snapshot.coveredIds));
    },
    publish: (filterId, nextLabels) => {
      if (
        Object.prototype.hasOwnProperty.call(labelsByFilterId, filterId)
        && sameLabelMap(labelsByFilterId[filterId], nextLabels)
      ) {
        return;
      }
      labelsByFilterId = { ...labelsByFilterId, [filterId]: nextLabels };
      emit(new Set(snapshot.coveredIds));
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => snapshot,
    getServerSnapshot: () => serverSnapshot,
  };
};
