export interface OperationProgressRequestGuard {
  begin: () => number;
  invalidate: () => void;
  shouldContinue: (generation?: number) => boolean;
}

export const createOperationProgressRequestGuard =
  (): OperationProgressRequestGuard => {
    let generation = 0;
    let alive = false;

    return {
      begin: () => {
        alive = true;
        generation += 1;
        return generation;
      },
      invalidate: () => {
        alive = false;
        generation += 1;
      },
      shouldContinue: (expectedGeneration?: number) => {
        if (!alive) {
          return false;
        }
        if (
          expectedGeneration !== undefined &&
          expectedGeneration !== generation
        ) {
          return false;
        }
        return true;
      },
    };
  };
