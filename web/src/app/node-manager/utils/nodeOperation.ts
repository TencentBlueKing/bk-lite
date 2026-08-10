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

  return uniqueOS.length !== 1;
};

export const buildControllerUninstallRow = (node: TableDataItem) => {
  const isWindows = node.operating_system === 'windows';
  const nodeId = node.id ?? node.key;
  return {
    id: nodeId,
    node_id: nodeId,
    os: node.operating_system,
    ip: node.ip,
    port: isWindows ? 5986 : 22,
    username: isWindows ? 'Administrator' : 'root',
    auth_type: 'password',
    password: '',
    private_key: '',
    key_file_name: undefined,
    winrm_scheme: 'https',
    winrm_transport: 'ntlm',
    winrm_cert_validation: true
  };
};

export const buildControllerUninstallRequestNode = (row: TableDataItem) => ({
  node_id: row.node_id ?? row.id,
  os: row.os,
  ip: row.ip,
  port: row.port,
  username: row.username,
  password: row.private_key ? '' : row.password,
  private_key: row.os === 'windows' ? '' : row.private_key || '',
  winrm_scheme: row.winrm_scheme || 'https',
  winrm_transport: row.winrm_transport || 'ntlm',
  winrm_cert_validation: row.winrm_cert_validation !== false
});

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
