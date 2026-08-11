import type {
  ControllerInstallProgressRow,
  RetryInstallParams
} from '@/app/node-manager/types/controller';
import type { Key } from 'react';

export interface RetryInstallNode extends ControllerInstallProgressRow {
  task_id?: Key;
}

export interface RetryInstallFormValues {
  port: number;
  username: string;
  password?: string;
  auth_type: 'password' | 'private_key';
  winrm_scheme?: 'https';
  winrm_transport?: 'ntlm';
  winrm_cert_validation?: boolean;
}

export const getRetryInstallInitialValues = (
  node: RetryInstallNode
): RetryInstallFormValues => {
  const isWindows = node.os === 'windows';

  return {
    port: node.port || (isWindows ? 5986 : 22),
    username: node.username || (isWindows ? 'Administrator' : 'root'),
    auth_type: 'password',
    winrm_scheme: isWindows ? node.winrm_scheme || 'https' : undefined,
    winrm_transport: isWindows ? node.winrm_transport || 'ntlm' : undefined,
    winrm_cert_validation: isWindows
      ? node.winrm_cert_validation ?? false
      : undefined
  };
};

export const validateWindowsRetryPort = (port?: number) => {
  return port !== 5985;
};

export const buildRetryInstallParams = (
  node: RetryInstallNode,
  values: RetryInstallFormValues,
  privateKey: string
): RetryInstallParams => {
  const isWindows = node.os === 'windows';
  const params: RetryInstallParams = {
    task_id: node.task_id,
    task_node_ids: node.task_node_id === undefined ? [] : [node.task_node_id],
    port: values.port,
    username: values.username,
    password: privateKey ? '' : values.password,
    private_key: isWindows ? '' : privateKey || ''
  };

  if (isWindows) {
    params.winrm_scheme = values.winrm_scheme || 'https';
    params.winrm_transport = values.winrm_transport || 'ntlm';
    params.winrm_cert_validation = values.winrm_cert_validation ?? false;
  }

  return params;
};
