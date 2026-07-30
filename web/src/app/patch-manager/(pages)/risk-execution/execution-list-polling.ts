export interface ExecutionListQuery {
  page: number;
  pageSize: number;
  search: string;
  taskType?: 'install' | 'reboot';
}

type LoadExecutionList = (
  query: ExecutionListQuery,
  silent: boolean,
) => Promise<void> | void;

export function createExecutionListPolling(
  load: LoadExecutionList,
  intervalMs = 2000,
) {
  let timer: ReturnType<typeof setInterval> | undefined;
  let generation = 0;

  const stop = () => {
    generation += 1;
    if (timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };

  const restart = (query: ExecutionListQuery) => {
    stop();
    const currentGeneration = generation;
    const snapshot = { ...query };
    let requesting = false;

    const request = async (silent: boolean) => {
      if (requesting || currentGeneration !== generation) return;
      requesting = true;
      try {
        await load(snapshot, silent);
      } finally {
        requesting = false;
      }
    };

    void request(false);
    timer = setInterval(() => {
      void request(true);
    }, intervalMs);
  };

  return { restart, stop };
}
