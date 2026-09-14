export interface LoginAuthRequestGuard {
  begin: () => number;
  invalidate: () => void;
  shouldContinue: (generation: number) => boolean;
}

export function createLoginAuthRequestGuard(): LoginAuthRequestGuard {
  let generation = 0;
  let alive = true;

  return {
    begin() {
      generation += 1;
      alive = true;
      return generation;
    },
    invalidate() {
      alive = false;
    },
    shouldContinue(targetGeneration: number) {
      return alive && targetGeneration === generation;
    },
  };
}
