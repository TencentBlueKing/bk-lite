interface DatasetVersionOption {
  label: string;
  value: string;
}

interface DatasetVersionRestoreParams {
  restoreVersion?: string | number | null;
  options: DatasetVersionOption[];
  allowRestore: boolean;
}

interface DatasetVersionRequestMatchParams {
  requestGeneration: number;
  currentGeneration: number;
  requestedDataset: number;
  currentDataset: number;
}

interface DatasetVersionRequestState {
  generation: number;
  dataset: number | null;
}

const isVersionInOptions = (
  restoreVersion: string | number | null | undefined,
  options: DatasetVersionOption[],
): string | undefined => {
  if (restoreVersion == null || restoreVersion === '') {
    return undefined;
  }
  const value = String(restoreVersion);
  return options.some((item) => String(item.value) === value) ? value : undefined;
};

export const resolveDatasetVersionRestore = ({
  restoreVersion,
  options,
  allowRestore,
}: DatasetVersionRestoreParams): string | undefined => {
  if (!allowRestore) {
    return undefined;
  }
  return isVersionInOptions(restoreVersion, options);
};

export const shouldApplyDatasetVersionResponse = ({
  requestGeneration,
  currentGeneration,
  requestedDataset,
  currentDataset,
}: DatasetVersionRequestMatchParams): boolean => {
  return requestGeneration === currentGeneration && requestedDataset === currentDataset;
};

export const createDatasetVersionRequestState = (): DatasetVersionRequestState => ({
  generation: 0,
  dataset: null,
});

export const beginDatasetVersionRequest = (
  state: DatasetVersionRequestState,
  dataset: number,
): { generation: number; dataset: number } => {
  state.generation += 1;
  state.dataset = dataset;
  return {
    generation: state.generation,
    dataset,
  };
};
