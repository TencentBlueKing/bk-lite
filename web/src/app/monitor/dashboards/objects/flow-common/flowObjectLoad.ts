export interface FlowObjectLoadTicket {
  generation: number;
}

export interface FlowObjectLoadCoordinator {
  begin: (isLoading: boolean) => FlowObjectLoadTicket | null;
  shouldApply: (ticket: FlowObjectLoadTicket) => boolean;
  invalidate: () => void;
}

export function shouldReloadFlowObjectsForFetcherIdentity(
  _previousFetcher: unknown,
  _nextFetcher: unknown,
): boolean {
  return false;
}

export function createFlowObjectLoadCoordinator(): FlowObjectLoadCoordinator {
  let generation = 0;

  return {
    begin(isLoading) {
      if (isLoading) return null;
      generation += 1;
      return { generation };
    },
    shouldApply(ticket) {
      return ticket.generation === generation;
    },
    invalidate() {
      generation += 1;
    },
  };
}
