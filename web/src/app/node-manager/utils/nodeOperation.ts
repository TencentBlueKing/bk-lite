import type { TableDataItem } from '../types';

export type CollectorOperationSelection =
  | {
    disabled: true;
    reason:
    | 'no_selection'
    | 'mixed_operating_system'
    | 'mixed_cpu_architecture'
    | 'unknown_architecture';
  }
  | {
    disabled: false;
    operatingSystem: string;
    cpuArchitecture: string;
  };

export const isControllerOperationDisabled = (selectedNodes: TableDataItem[]) => {
  if (!selectedNodes.length) return true;

  const operatingSystems = selectedNodes.map((node) => node.operating_system);
  const uniqueOS = [...new Set(operatingSystems)];

  return uniqueOS.length !== 1 || operatingSystems.includes('windows');
};

const normalizeText = (value: unknown) => {
  return typeof value === 'string' ? value.trim() : '';
};

export const getCollectorOperationSelection = (
  selectedNodes: TableDataItem[]
): CollectorOperationSelection => {
  if (!selectedNodes.length) {
    return { disabled: true, reason: 'no_selection' };
  }

  const operatingSystems = selectedNodes.map((node) =>
    normalizeText(node.operating_system)
  );
  const cpuArchitectures = selectedNodes.map((node) =>
    normalizeText(node.cpu_architecture)
  );
  const uniqueOS = [...new Set(operatingSystems)];
  const uniqueArchitectures = [...new Set(cpuArchitectures)];

  if (uniqueOS.length !== 1) {
    return { disabled: true, reason: 'mixed_operating_system' };
  }
  if (uniqueArchitectures.length !== 1) {
    return { disabled: true, reason: 'mixed_cpu_architecture' };
  }
  if (!uniqueArchitectures[0]) {
    return { disabled: true, reason: 'unknown_architecture' };
  }

  return {
    disabled: false,
    operatingSystem: uniqueOS[0],
    cpuArchitecture: uniqueArchitectures[0]
  };
};

export const buildCollectorOperationListParams = ({
  operatingSystem,
  cpuArchitecture,
  typeTag
}: {
  operatingSystem: string;
  cpuArchitecture: string;
  typeTag?: string;
}) => {
  const params: {
    node_operating_system: string;
    cpu_architecture: string;
    tags?: string;
  } = {
    node_operating_system: operatingSystem,
    cpu_architecture: cpuArchitecture
  };

  if (typeTag) {
    params.tags = typeTag;
  }

  return params;
};
