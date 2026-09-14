export interface NodeTopPodLoadKey {
  idValuesKey: string;
  interval: string | number | undefined;
  timeKey: string;
  isDashboardMode: boolean;
  loadTick: number;
}

export interface NodeTopPodLoadCoordinator {
  begin: () => number;
  shouldApply: (generation: number) => boolean;
}

export function shouldReloadNodeTopPods(
  previous: NodeTopPodLoadKey | null,
  next: NodeTopPodLoadKey
): boolean {
  if (!next.isDashboardMode || !next.idValuesKey) {
    return false;
  }
  if (!previous) {
    return true;
  }
  return (
    previous.idValuesKey !== next.idValuesKey ||
    previous.interval !== next.interval ||
    previous.timeKey !== next.timeKey ||
    previous.isDashboardMode !== next.isDashboardMode ||
    previous.loadTick !== next.loadTick
  );
}

export function createNodeTopPodLoadCoordinator(): NodeTopPodLoadCoordinator {
  let generation = 0;
  return {
    begin() {
      generation += 1;
      return generation;
    },
    shouldApply(targetGeneration: number) {
      return targetGeneration === generation;
    },
  };
}
