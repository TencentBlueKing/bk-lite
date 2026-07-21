export interface LatestRequestGuard {
  begin: () => number;
  commitIfCurrent: (requestId: number, commit: () => void) => boolean;
  invalidate: () => void;
}

export const createLatestRequestGuard = (): LatestRequestGuard => {
  let currentRequestId = 0;

  return {
    begin: () => ++currentRequestId,
    commitIfCurrent: (requestId, commit) => {
      if (requestId !== currentRequestId) {
        return false;
      }

      commit();
      return true;
    },
    invalidate: () => {
      currentRequestId += 1;
    },
  };
};
