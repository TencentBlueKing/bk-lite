'use client';

import React, { useEffect, useId, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Input,
  InputNumber,
  Popover,
  Select,
  Switch,
  Tooltip,
} from 'antd';
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import {
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  HolderOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  SyncOutlined,
} from '@ant-design/icons';

import SortableItem from '@/app/cmdb/components/sortable-item';
import {
  MAX_CREDENTIAL_POOL_SIZE,
  PASSWORD_PLACEHOLDER,
  SNMP_INTEGRITY_OPTIONS,
  SNMP_PRIVACY_OPTIONS,
} from '@/app/cmdb/constants/professCollection';
import {
  CredentialPoolItem,
  CredentialSchema,
} from '@/app/cmdb/types/autoDiscovery';
import { useTranslation } from '@/utils/i18n';
import CredentialPicker from '@/components/credential-picker';
import { isVaultAuthField } from '../utils/vaultAuthFields';
import type { CredentialHelpDefinition } from './credentialHelp';

import styles from '../index.module.scss';

type CredentialShape = 'ssh' | 'sql' | 'snmp' | 'config_file' | 'network_config_file' | 'vm' | 'winsphere' | 'cloud' | 'ipmi' | 'redfish' | 'winrm' | 'macos_ssh' | 'influxdb' | 'platform_api';
interface CredentialDragEndEvent {
  active: { id: string | number };
  over: { id: string | number } | null;
}

const IPMI_PRIVILEGE_OPTIONS = [
  { label: 'callback', value: 'callback' },
  { label: 'user', value: 'user' },
  { label: 'operator', value: 'operator' },
  { label: 'administrator', value: 'administrator' },
];

const NETWORK_SSH_DEFAULT_PORT = 22;
const NETWORK_TELNET_DEFAULT_PORT = 23;

function normalizeNetworkTransport(value?: string): 'ssh' | 'telnet' {
  return String(value || 'ssh').trim().toLowerCase() === 'telnet' ? 'telnet' : 'ssh';
}

function defaultPortForNetworkTransport(protocol: 'ssh' | 'telnet'): number {
  return protocol === 'telnet' ? NETWORK_TELNET_DEFAULT_PORT : NETWORK_SSH_DEFAULT_PORT;
}

function portForNetworkTransportSwitch(currentPort: unknown, nextProtocol: 'ssh' | 'telnet'): number {
  const numeric = Number(currentPort);
  const previousDefault = nextProtocol === 'telnet' ? NETWORK_SSH_DEFAULT_PORT : NETWORK_TELNET_DEFAULT_PORT;
  if (currentPort === undefined || currentPort === null || currentPort === '' || numeric === previousDefault) {
    return defaultPortForNetworkTransport(nextProtocol);
  }
  return Number.isFinite(numeric) ? numeric : defaultPortForNetworkTransport(nextProtocol);
}

export interface CredentialPoolEditorProps {
  value?: CredentialPoolItem[];
  maxCount?: number;
  credentialShape: CredentialShape;
  onChange?: (value: CredentialPoolItem[]) => void;
  editMode?: boolean;
  showDatabase?: boolean;
  showPort?: boolean;
  allowAdd?: boolean;
  allowRemove?: boolean;
  showCount?: boolean;
  cloudRegionOptions?: { label: string; value: string }[];
  cloudRegionLoading?: boolean;
  onCloudRegionRefresh?: () => void;
  onCredentialFieldChange?: (field: string) => void;
  credentialHelp?: CredentialHelpDefinition;
  cloudCredentialLabels?: {
    accessKey: string;
    accessSecret: string;
    projectId?: string;
  };
  defaultPort?: number | string;
  credentialSchema?: CredentialSchema;
  vaultCategory?: string | null;
  vaultTypeKeys?: string[];
  collectModelId?: string;
}

const VAULT_META_KEYS = new Set([
  'credential_id', 'credential_version', 'credential_source',
  'vault_credential_id', 'vault_actor_context', '_client_id',
  'vault_type_key',
]);

function renderVaultDynamicFields(
  item: CredentialPoolItem,
  index: number,
  shape: CredentialShape,
  updateItem: (index: number, patch: Partial<CredentialPoolItem>) => void,
  t: (key: string, defaultMessage?: string) => string,
  showPort: boolean,
  onCloudRegionRefresh?: () => void,
  cloudRegionLoading?: boolean,
  collectModelId?: string,
  cloudRegionOptions: { label: string; value: string }[] = [],
  cloudCredentialLabels?: {
    accessKey: string;
    accessSecret: string;
    projectId?: string;
  },
): React.ReactNode {
  const known = new Set([
    'port', 'snmp_port', 'https_port', 'database', 'scheme', 'verify_tls',
    'transport_protocol', 'privilege', 'ssl', 'regionId', 'regionName',
    'source', 'user_type', 'subscription_id', 'enable_password', 'project_id',
    'projectId',
  ]);
  const portKey = shape === 'snmp' ? 'snmp_port' : shape === 'winsphere' ? 'https_port' : 'port';
  const extras = Object.entries(item).filter(([key, value]) =>
    !VAULT_META_KEYS.has(key) && !isVaultAuthField(key, item) && !known.has(key)
    && value !== undefined && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
  );
  return (
    <div className={styles.credentialFieldGrid}>
      {(shape === 'network_config_file' || item.transport_protocol !== undefined) && (
        <>
          <InputRow label={t('Collection.credentialPool.transportProtocol', '连接协议')}>
            <Select
              value={normalizeNetworkTransport(item.transport_protocol)}
              options={[
                { label: 'SSH', value: 'ssh' },
                { label: 'Telnet', value: 'telnet' },
              ]}
              onChange={(nextValue) => {
                const transport_protocol = normalizeNetworkTransport(nextValue);
                updateItem(index, {
                  transport_protocol,
                  port: portForNetworkTransportSwitch(item.port, transport_protocol),
                });
              }}
            />
          </InputRow>
          {normalizeNetworkTransport(item.transport_protocol) === 'telnet' && (
            <Alert
              type="warning"
              showIcon
              message={t(
                'Collection.credentialPool.telnetWarning',
                'Telnet 明文传输账号口令，仅应在隔离管理网或设备只开放 TCP/23 时使用。',
              )}
            />
          )}
        </>
      )}
      {(shape !== 'cloud' && (showPort || shape === 'snmp' || shape === 'winsphere')) && (
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber className="!w-full" min={1} max={65535} value={item[portKey]}
            onChange={(next) => updateItem(index, { [portKey]: next ?? undefined })} />
        </InputRow>
      )}
      {shape === 'cloud' && cloudCredentialLabels?.projectId && (
        <InputRow label={cloudCredentialLabels.projectId}>
          <Input
            value={item.projectId}
            placeholder={t('common.inputTip', '请输入')}
            onChange={(event) => updateItem(index, {
              projectId: event.target.value,
              regionId: undefined,
              regionName: undefined,
            })}
          />
        </InputRow>
      )}
      {shape === 'cloud' && (
        <InputRow label={t('Collection.cloudTask.region', '区域')}>
          <div className={styles.credentialInlineControl}>
            <Select
              value={item.regionId}
              onChange={(nextValue, option) => {
                const label = Array.isArray(option) ? option[0]?.label : option?.label;
                updateItem(index, { regionId: nextValue, regionName: typeof label === 'string' ? label : undefined });
              }}
              loading={cloudRegionLoading}
              placeholder={t('common.selectTip', '请选择')}
              options={cloudRegionOptions}
            />
            <Button
              type="text"
              aria-label={t('common.refresh')}
              icon={<SyncOutlined spin={cloudRegionLoading} aria-hidden />}
              onClick={onCloudRegionRefresh}
              className={styles.credentialRefreshButton}
            />
          </div>
        </InputRow>
      )}
      {collectModelId === 'smartx' && (
        <InputRow label={t('Collection.smartxTask.source', '认证来源')}>
          <Input value={item.source || 'LOCAL'} onChange={(event) => updateItem(index, { source: event.target.value })} />
        </InputRow>
      )}
      {collectModelId === 'fusioncompute' && (
        <InputRow label={t('Collection.fusioncomputeTask.userType', '用户类型')}>
          <Input value={item.user_type ?? '0'} onChange={(event) => updateItem(index, { user_type: event.target.value })} />
        </InputRow>
      )}
      {collectModelId === 'azure' && (
        <InputRow label={t('Collection.azureTask.subscriptionId', '订阅 ID')}>
          <Input value={item.subscription_id} onChange={(event) => updateItem(index, { subscription_id: event.target.value })} />
        </InputRow>
      )}
      {collectModelId === 'openstack' && (
        <InputRow label={t('Collection.platformApiTask.projectId', '项目 ID')} required={false}>
          <Input value={item.project_id} onChange={(event) => updateItem(index, { project_id: event.target.value })} />
        </InputRow>
      )}
      {(shape === 'sql' && item.database !== undefined) && (
        <InputRow label={t('Collection.database', '数据库')}>
          <Input value={item.database} onChange={(event) => updateItem(index, { database: event.target.value })} />
        </InputRow>
      )}
      {(shape === 'influxdb' || item.scheme !== undefined) && (
        <InputRow label={t('Collection.influxdbTask.scheme', '连接协议')}>
          <Select value={item.scheme || 'http'} options={['http', 'https'].map((value) => ({ label: value.toUpperCase(), value }))}
            onChange={(scheme) => updateItem(index, { scheme })} />
        </InputRow>
      )}
      {shape === 'network_config_file' && item.vault_type_key !== 'network_cli' && (
        <InputRow label={t('Collection.credentialPool.enablePassword', '特权密码')} required={false}>
          <Input.Password value={item.enable_password} autoComplete="new-password"
            onChange={(event) => updateItem(index, { enable_password: event.target.value })} />
        </InputRow>
      )}
      {item.privilege !== undefined && (
        <InputRow label={t('Collection.IPMITask.privilege', '权限级别')}>
          <Select value={item.privilege} options={IPMI_PRIVILEGE_OPTIONS}
            onChange={(privilege) => updateItem(index, { privilege })} />
        </InputRow>
      )}
      {item.verify_tls !== undefined && (
        <InputRow label={t('Collection.influxdbTask.verifyTls', '校验证书')}>
          <Switch disabled={collectModelId === 'smartx'}
            checked={collectModelId === 'smartx' || item.verify_tls !== false}
            onChange={(verify_tls) => updateItem(index, { verify_tls })} />
        </InputRow>
      )}
      {item.ssl !== undefined && (
        <InputRow label={t('Collection.VMTask.sslVerify', 'SSL 验证')}>
          <Switch checked={Boolean(item.ssl)} onChange={(ssl) => updateItem(index, { ssl })} />
        </InputRow>
      )}
      {extras.map(([key, value]) => (
        <InputRow key={key} label={t(`Collection.${key}`, key)}>
          {typeof value === 'boolean'
            ? <Switch checked={value} onChange={(next) => updateItem(index, { [key]: next })} />
            : <Input disabled={collectModelId === 'manageone' && key === 'api_version'} value={value} onChange={(event) => updateItem(index, { [key]: event.target.value })} />}
        </InputRow>
      ))}
    </div>
  );
}

const makeClientId = () => `cred-local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;

const ensureClientIds = (items: CredentialPoolItem[]) =>
  items.map((item) => ({
    ...item,
    _client_id: item._client_id || makeClientId(),
  }));

const withDefaultSnmpVersion = (item: CredentialPoolItem): CredentialPoolItem => {
  const version = String(item?.version || '').trim();
  if (version === 'v2' || version === 'v2c' || version === 'v3') {
    return item;
  }
  const community = String(item?.community || '').trim();
  const username = String(item?.username || '').trim();
  return {
    ...item,
    version: username && !community ? 'v3' : 'v2',
  };
};

const createEmptyCredential = (
  shape: CredentialShape,
  showDatabase?: boolean,
  defaultPort?: number | string,
  credentialSchema?: CredentialSchema,
  showPort: boolean = true,
): CredentialPoolItem => {
  if (shape === 'snmp') {
    return {
      _client_id: makeClientId(),
      version: 'v2',
      snmp_port: '161',
      level: 'authNoPriv',
      integrity: 'sha',
      privacy: 'aes',
    };
  }

  if (shape === 'winrm') {
    return {
      _client_id: makeClientId(),
      port: 5986,
      scheme: 'https',
      transport: 'ntlm',
      certValidation: false,
    };
  }

  if (shape === 'macos_ssh') {
    return {
      _client_id: makeClientId(),
      port: 22,
      authType: 'password',
    };
  }

  if (shape === 'influxdb') {
    return {
      _client_id: makeClientId(),
      scheme: 'http',
      port: 8086,
      verify_tls: true,
      token: '',
    };
  }

  if (shape === 'platform_api') {
    return {
      _client_id: makeClientId(),
      username: '',
      password: '',
      port: 443,
      verify_tls: true,
    };
  }

  if (shape === 'winsphere') {
    return {
      _client_id: makeClientId(),
      ...Object.fromEntries(
        (credentialSchema?.fields || []).map((field) => [
          field.key,
          field.default ?? (field.type === 'boolean' ? false : ''),
        ]),
      ),
    };
  }

  return {
    _client_id: makeClientId(),
    ...(showPort
      ? {
        port:
          shape === 'sql'
            ? (defaultPort ?? (showDatabase ? '1433' : '3306'))
            : shape === 'vm'
              ? '443'
              : '22',
      }
      : {}),
    ...(shape === 'vm' ? { ssl: false } : {}),
    ...(shape === 'cloud' ? { accessKey: '', accessSecret: '', regionId: '' } : {}),
    ...(shape === 'ipmi' ? { port: '623', privilege: 'administrator' } : {}),
    ...(shape === 'redfish' ? { port: '443', verify_tls: true } : {}),
    ...(shape === 'sql' && showDatabase ? { database: 'master' } : {}),
    ...(shape === 'network_config_file' ? { transport_protocol: 'ssh' } : {}),
  };
};

function getItemKey(item: CredentialPoolItem, index: number) {
  return String(item.credential_id || item._client_id || `credential-${index}`);
}

function getMaskedSecret(value?: string) {
  if (!value) {
    return '--';
  }
  return '••••••••••';
}

function getPreviewFields(
  item: CredentialPoolItem,
  shape: CredentialShape,
  t: (key: string, defaultMessage?: string) => string,
  passwordVisible: boolean,
  cloudCredentialLabels?: {
    accessKey: string;
    accessSecret: string;
    projectId?: string;
  },
  showPort: boolean = true,
) {
  if (shape === 'winsphere') {
    return [
      {
        label: t('Collection.WinSphereTask.user', 'WinSphere账号'),
        value: item.user || '--',
      },
      {
        label: t('password', '密码'),
        value: passwordVisible ? item.password || '--' : getMaskedSecret(item.password),
        isSecret: true,
      },
      {
        label: t('Collection.WinSphereTask.httpsPort', 'HTTPS端口'),
        value: String(item.https_port || 443),
      },
      {
        label: t('Collection.WinSphereTask.verifyTls', 'TLS证书校验'),
        value: item.verify_tls ? t('common.yes', '是') : t('common.no', '否'),
      },
    ];
  }

  if (shape === 'snmp') {
    const secretValue = item.version === 'v3' ? item.authkey : item.community;
    return [
      { label: t('Collection.SNMPTask.version', '版本'), value: item.version || 'v2' },
      {
        label: item.version === 'v3'
          ? t('Collection.SNMPTask.userName', '用户')
          : t('Collection.SNMPTask.communityString', '团体字'),
        value: item.version === 'v3' ? item.username || '--' : passwordVisible ? secretValue || '--' : getMaskedSecret(secretValue),
        isSecret: item.version !== 'v3',
      },
      { label: t('Collection.port', '端口'), value: String(item.snmp_port || 161) },
    ];
  }

  if (shape === 'cloud') {
    const fields = [
      {
        label: cloudCredentialLabels?.accessKey
          || t('Collection.cloudTask.accessKey', '访问密钥'),
        value: item.accessKey || '--',
      },
      {
        label: cloudCredentialLabels?.accessSecret
          || t('Collection.cloudTask.accessSecret', '访问密钥 Secret'),
        value: passwordVisible && item.accessSecret && item.accessSecret !== PASSWORD_PLACEHOLDER
          ? item.accessSecret
          : getMaskedSecret(item.accessSecret),
        isSecret: true,
      },
      { label: t('Collection.cloudTask.region', '区域'), value: item.regionName || item.regionId || '--' },
    ];
    if (cloudCredentialLabels?.projectId) {
      fields.splice(2, 0, {
        label: cloudCredentialLabels.projectId,
        value: item.projectId || '--',
        isSecret: false,
      });
    }
    return fields;
  }

  if (shape === 'winrm') {
    return [
      { label: t('user', '用户'), value: item.username || '--' },
      {
        label: t('password', '密码'),
        value: passwordVisible && item.password && item.password !== PASSWORD_PLACEHOLDER ? item.password : getMaskedSecret(item.password),
        isSecret: true,
      },
      { label: t('Collection.port', '端口'), value: String(item.port || 5986) },
      { label: t('Collection.PCTask.scheme', '协议'), value: (item.scheme || 'https').toUpperCase() },
    ];
  }

  if (shape === 'macos_ssh') {
    const isKeyAuth = item.authType === 'privateKey';
    const secretValue = isKeyAuth ? item.private_key : item.password;
    return [
      { label: t('user', '用户'), value: item.username || '--' },
      {
        label: isKeyAuth ? t('Collection.PCTask.privateKey', '私钥') : t('password', '密码'),
        value: passwordVisible && secretValue && secretValue !== PASSWORD_PLACEHOLDER ? secretValue : getMaskedSecret(secretValue),
        isSecret: true,
      },
      { label: t('Collection.port', '端口'), value: String(item.port || 22) },
    ];
  }

  if (shape === 'influxdb') {
    return [
      {
        label: t('Collection.influxdbTask.scheme', '连接协议'),
        value: String(item.scheme || 'http').toUpperCase(),
      },
      {
        label: t('Collection.port', '端口'),
        value: String(item.port || 8086),
      },
      {
        label: t('Collection.influxdbTask.operatorToken', 'Operator Token'),
        value: passwordVisible && item.token && item.token !== PASSWORD_PLACEHOLDER
          ? item.token
          : getMaskedSecret(item.token),
        isSecret: true,
      },
    ];
  }

  if (shape === 'platform_api') {
    return [
      { label: t('user', '用户'), value: item.username || '--' },
      {
        label: t('password', '密码'),
        value: passwordVisible && item.password && item.password !== PASSWORD_PLACEHOLDER
          ? item.password
          : getMaskedSecret(item.password),
        isSecret: true,
      },
      { label: t('Collection.port', '端口'), value: String(item.port || 443) },
      {
        label: t('Collection.influxdbTask.verifyTls', '校验证书'),
        value: item.verify_tls !== false ? t('common.yes', '是') : t('common.no', '否'),
      },
    ];
  }

  const username = shape === 'sql' ? item.user : item.username;
  const fields = [
    { label: shape === 'sql' || shape === 'vm' ? t('Collection.VMTask.username', '用户') : t('user', '用户'), value: username || '--' },
    {
      label: shape === 'sql' || shape === 'vm' ? t('Collection.VMTask.password', '密码') : t('password', '密码'),
      value: passwordVisible && item.password && item.password !== PASSWORD_PLACEHOLDER ? item.password : getMaskedSecret(item.password),
      isSecret: true,
    },
  ];
  if (showPort) {
    fields.push({
      label: t('Collection.port', '端口'),
      value: String(item.port || (shape === 'sql' ? '3306' : shape === 'vm' || shape === 'redfish' ? '443' : shape === 'ipmi' ? '623' : '22')),
    });
  }
  if (shape === 'redfish') {
    fields.push({
      label: t('Collection.RedfishTask.verifyTls', '校验证书'),
      value: item.verify_tls !== false ? t('common.yes', '是') : t('common.no', '否'),
    });
  }
  if (shape === 'network_config_file') {
    const transportProtocol = String(item.transport_protocol || 'ssh').toLowerCase() === 'telnet'
      ? 'telnet'
      : 'ssh';
    fields.splice(0, 0, {
      label: t('Collection.credentialPool.transportProtocol', '连接协议'),
      value: transportProtocol === 'telnet' ? 'Telnet' : 'SSH',
    });
    fields.push({
      label: t('Collection.credentialPool.enablePassword', '特权密码'),
      value: passwordVisible && item.enable_password && item.enable_password !== PASSWORD_PLACEHOLDER
        ? item.enable_password
        : getMaskedSecret(item.enable_password),
      isSecret: true,
    });
  }
  return fields;
}

function CredentialMetaField({
  field,
  passwordVisible,
  onToggleSecret,
  toggleSecretLabel,
}: {
  field: { label: string; value: string; isSecret?: boolean };
  passwordVisible: boolean;
  onToggleSecret: (event: React.MouseEvent<HTMLElement>) => void;
  toggleSecretLabel: string;
}) {
  return (
    <div className={`${styles.credentialMetaItem} ${field.value === '--' ? styles.credentialMetaEmpty : ''}`}>
      <span className={styles.credentialMetaLabel}>{field.label}</span>
      <span className={styles.credentialMetaValue}>{field.value}</span>
      {field.isSecret && (
        <Button
          type="text"
          size="small"
          className={styles.credentialMetaToggle}
          aria-label={toggleSecretLabel}
          icon={passwordVisible
            ? <EyeInvisibleOutlined aria-hidden="true" />
            : <EyeOutlined aria-hidden="true" />}
          onClick={onToggleSecret}
        />
      )}
    </div>
  );
}

function SecretInput({
  id,
  value,
  placeholder,
  editMode,
  onChange,
}: {
  id?: string;
  value?: string;
  placeholder: string;
  editMode: boolean;
  onChange: (nextValue: string) => void;
}) {
  return (
    <Input.Password
      id={id}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      onFocus={(event) => {
        if (!editMode) {
          return;
        }
        if (event.target.value === PASSWORD_PLACEHOLDER) {
          onChange('');
        }
      }}
      onBlur={(event) => {
        if (!editMode) {
          return;
        }
        if (!event.target.value?.trim()) {
          onChange(PASSWORD_PLACEHOLDER);
        }
      }}
    />
  );
}

function InputRow({
  label,
  children,
  required = true,
  htmlFor,
  help,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
  htmlFor?: string;
  help?: string;
}) {
  return (
    <div className={styles.credentialFieldRow}>
      <label className={styles.credentialFieldLabel} htmlFor={htmlFor}>
        {required && <span className={styles.credentialRequiredMark}>*</span>}
        <span>{label}</span>
        {help && (
          <Tooltip title={help}>
            <QuestionCircleOutlined aria-label={help} />
          </Tooltip>
        )}
      </label>
      <div className={styles.credentialFieldControl}>{children}</div>
    </div>
  );
}

function renderCredentialFields({
  collectModelId,
  item,
  index,
  shape,
  editMode,
  showDatabase,
  showPort,
  cloudRegionOptions,
  cloudRegionLoading,
  onCloudRegionRefresh,
  onCredentialFieldChange,
  cloudCredentialLabels,
  credentialSchema,
  t,
  updateItem,
}: {
  collectModelId?: string;
  item: CredentialPoolItem;
  index: number;
  shape: CredentialShape;
  editMode: boolean;
  showDatabase: boolean;
  showPort: boolean;
  cloudRegionOptions: { label: string; value: string }[];
  cloudRegionLoading: boolean;
  onCloudRegionRefresh?: () => void;
  onCredentialFieldChange?: (field: string) => void;
  cloudCredentialLabels?: {
    accessKey: string;
    accessSecret: string;
    projectId?: string;
  };
  credentialSchema?: CredentialSchema;
  t: (key: string, defaultMessage?: string) => string;
  updateItem: (index: number, patch: Partial<CredentialPoolItem>) => void;
}) {
  if (shape === 'winsphere') {
    return (
      <div className={styles.credentialFieldGrid}>
        {credentialSchema?.fields.map((field) => {
          const inputId = `winsphere-credential-${index}-${field.key}`;
          const label = t(field.label_key || field.key, field.label);
          const help = field.help
            ? t(field.help_key || `${field.key}.help`, field.help)
            : undefined;
          let control: React.ReactNode;
          if (field.type === 'password') {
            control = (
              <SecretInput
                id={inputId}
                value={item[field.key]}
                placeholder={t('common.inputTip', '请输入')}
                editMode={editMode}
                onChange={(value) => updateItem(index, { [field.key]: value })}
              />
            );
          } else if (field.type === 'integer') {
            control = (
              <InputNumber
                id={inputId}
                min={field.min}
                max={field.max}
                className="!w-full"
                value={item[field.key]}
                onChange={(value) =>
                  updateItem(index, { [field.key]: value ?? undefined })
                }
              />
            );
          } else if (field.type === 'boolean') {
            control = (
              <Switch
                id={inputId}
                checked={Boolean(item[field.key])}
                onChange={(value) => updateItem(index, { [field.key]: value })}
              />
            );
          } else {
            control = (
              <Input
                id={inputId}
                value={item[field.key]}
                placeholder={t('common.inputTip', '请输入')}
                onChange={(event) =>
                  updateItem(index, { [field.key]: event.target.value })
                }
              />
            );
          }
          return (
            <InputRow
              key={field.key}
              label={label}
              required={field.required}
              htmlFor={inputId}
              help={help}
            >
              {control}
            </InputRow>
          );
        })}
        {item.verify_tls === false && (
          <Alert
            type="warning"
            showIcon
            message={t(
              'Collection.platformApiTask.tlsWarning',
              '关闭证书校验会增加中间人攻击风险，仅应临时用于受信任网络中的自签名证书。',
            )}
          />
        )}
      </div>
    );
  }

  if (shape === 'snmp') {
    const version = item.version || 'v2';
    const level = item.level || 'authNoPriv';
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('Collection.SNMPTask.version', '版本')}>
          <Select value={version} onChange={(nextValue) => updateItem(index, { version: nextValue })}>
            <Select.Option value="v2">V2</Select.Option>
            <Select.Option value="v2c">V2C</Select.Option>
            <Select.Option value="v3">V3</Select.Option>
          </Select>
        </InputRow>
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.snmp_port}
            onChange={(nextValue) => updateItem(index, { snmp_port: nextValue ?? undefined })}
          />
        </InputRow>

        {version !== 'v3' ? (
          <InputRow label={t('Collection.SNMPTask.communityString', '团体字')}>
            <SecretInput
              value={item.community}
              placeholder={t('common.inputTip', '请输入')}
              editMode={editMode}
              onChange={(nextValue) => updateItem(index, { community: nextValue })}
            />
          </InputRow>
        ) : (
          <>
            <InputRow label={t('Collection.SNMPTask.securityLevel', '安全级别')}>
              <Select value={level} onChange={(nextValue) => updateItem(index, { level: nextValue })}>
                <Select.Option value="authNoPriv">{t('Collection.SNMPTask.authNoPriv', '认证不加密')}</Select.Option>
                <Select.Option value="authPriv">{t('Collection.SNMPTask.authPriv', '认证加密')}</Select.Option>
              </Select>
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.userName', '用户')}>
              <Input
                value={item.username}
                placeholder={t('common.inputTip', '请输入')}
                onChange={(event) => updateItem(index, { username: event.target.value })}
              />
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.authPassword', '认证密码')}>
              <SecretInput
                value={item.authkey}
                placeholder={t('common.inputTip', '请输入')}
                editMode={editMode}
                onChange={(nextValue) => updateItem(index, { authkey: nextValue })}
              />
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.hashAlgorithm', '哈希算法')}>
              <Select
                value={item.integrity || 'sha'}
                options={[...SNMP_INTEGRITY_OPTIONS]}
                onChange={(nextValue) => updateItem(index, { integrity: nextValue })}
              />
            </InputRow>
            {level === 'authPriv' && (
              <>
                <InputRow label={t('Collection.SNMPTask.encryptAlgorithm', '加密算法')}>
                  <Select
                    value={item.privacy || 'aes'}
                    options={[...SNMP_PRIVACY_OPTIONS]}
                    onChange={(nextValue) => updateItem(index, { privacy: nextValue })}
                  />
                </InputRow>
                <InputRow label={t('Collection.SNMPTask.encryptKey', '加密密钥')}>
                  <SecretInput
                    value={item.privkey}
                    placeholder={t('common.inputTip', '请输入')}
                    editMode={editMode}
                    onChange={(nextValue) => updateItem(index, { privkey: nextValue })}
                  />
                </InputRow>
              </>
            )}
          </>
        )}
      </div>
    );
  }

  if (shape === 'winrm') {
    const scheme = item.scheme || 'https';
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('user', '用户')}>
          <Input
            value={item.username}
            placeholder={t('Collection.PCTask.usernameTip', '支持域、本地和 UPN 表达')}
            onChange={(event) => updateItem(index, { username: event.target.value })}
          />
        </InputRow>
        <InputRow label={t('password', '密码')}>
          <SecretInput
            value={item.password}
            placeholder={t('common.inputTip', '请输入')}
            editMode={editMode}
            onChange={(nextValue) => updateItem(index, { password: nextValue })}
          />
        </InputRow>
        <InputRow label={t('Collection.PCTask.scheme', '协议')}>
          <Select
            value={scheme}
            onChange={(nextValue) =>
              updateItem(index, {
                scheme: nextValue,
                port: nextValue === 'https' ? 5986 : 5985,
              })
            }
            options={[
              { label: 'HTTPS', value: 'https' },
              { label: 'HTTP', value: 'http' },
            ]}
          />
        </InputRow>
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.port}
            onChange={(nextValue) => updateItem(index, { port: nextValue ?? undefined })}
          />
        </InputRow>
        <InputRow label={t('Collection.PCTask.transport', '认证方式')} required={false}>
          <Input value="NTLM" disabled />
        </InputRow>
        <InputRow label={t('Collection.PCTask.certValidation', '证书校验')} required={false}>
          <Switch
            checked={Boolean(item.certValidation)}
            onChange={(checked) => updateItem(index, { certValidation: checked })}
          />
        </InputRow>
        {(scheme === 'http' || !item.certValidation) && (
          <Alert
            type="warning"
            showIcon
            message={
              scheme === 'http'
                ? t('Collection.PCTask.winrmHttpWarning', 'HTTP 明文传输凭据，仅建议在受信网络使用')
                : t('Collection.PCTask.winrmCertWarning', '关闭证书校验存在中间人攻击风险')
            }
          />
        )}
      </div>
    );
  }

  if (shape === 'macos_ssh') {
    const authType = item.authType || 'password';
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('user', '用户')}>
          <Input
            value={item.username}
            placeholder={t('common.inputTip', '请输入')}
            onChange={(event) => updateItem(index, { username: event.target.value })}
          />
        </InputRow>
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.port}
            onChange={(nextValue) => updateItem(index, { port: nextValue ?? undefined })}
          />
        </InputRow>
        <InputRow label={t('Collection.PCTask.authType', '认证方式')}>
          <Select
            value={authType}
            onChange={(nextValue) =>
              updateItem(
                index,
                nextValue === 'privateKey'
                  ? { authType: nextValue, password: '' }
                  : { authType: nextValue, private_key: '', passphrase: '' }
              )
            }
            options={[
              { label: t('Collection.PCTask.authTypePassword', '密码'), value: 'password' },
              { label: t('Collection.PCTask.authTypePrivateKey', 'PEM 私钥'), value: 'privateKey' },
            ]}
          />
        </InputRow>
        {authType === 'privateKey' ? (
          <>
            <InputRow label={t('Collection.PCTask.privateKey', '私钥')}>
              <Input.TextArea
                rows={4}
                value={item.private_key === PASSWORD_PLACEHOLDER ? '' : item.private_key}
                placeholder={t('Collection.PCTask.privateKeyTip', '粘贴 PEM 格式私钥')}
                onChange={(event) => updateItem(index, { private_key: event.target.value })}
              />
            </InputRow>
            <InputRow label={t('Collection.PCTask.passphrase', '密码短语')} required={false}>
              <SecretInput
                value={item.passphrase}
                placeholder={t('Collection.PCTask.passphraseTip', '私钥有密码短语时填写')}
                editMode={editMode}
                onChange={(nextValue) => updateItem(index, { passphrase: nextValue })}
              />
            </InputRow>
          </>
        ) : (
          <InputRow label={t('password', '密码')}>
            <SecretInput
              value={item.password}
              placeholder={t('common.inputTip', '请输入')}
              editMode={editMode}
              onChange={(nextValue) => updateItem(index, { password: nextValue })}
            />
          </InputRow>
        )}
      </div>
    );
  }

  if (shape === 'cloud') {
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow
          label={cloudCredentialLabels?.accessKey || t('Collection.cloudTask.accessKey', '访问密钥')}
        >
          <Input
            value={item.accessKey}
            placeholder={t('common.inputTip', '请输入')}
            onChange={(event) => {
              updateItem(index, {
                accessKey: event.target.value,
                ...(editMode && item.accessSecret === PASSWORD_PLACEHOLDER ? { accessSecret: '' } : {}),
                regionId: undefined,
                regionName: undefined,
              });
              onCredentialFieldChange?.('accessKey');
            }}
            onFocus={(event) => {
              if (!editMode) {
                return;
              }
              if (event.target.value === PASSWORD_PLACEHOLDER) {
                updateItem(index, { accessKey: '' });
              }
            }}
            onBlur={(event) => {
              if (!editMode) {
                return;
              }
              if (!event.target.value?.trim()) {
                updateItem(index, { accessKey: PASSWORD_PLACEHOLDER });
              }
            }}
          />
        </InputRow>
        <InputRow
          label={cloudCredentialLabels?.accessSecret || t('Collection.cloudTask.accessSecret', '访问密钥 Secret')}
        >
          <SecretInput
            value={item.accessSecret}
            placeholder={t('common.inputTip', '请输入')}
            editMode={editMode}
            onChange={(nextValue) => {
              updateItem(index, {
                accessSecret: nextValue,
                ...(editMode && item.accessKey === PASSWORD_PLACEHOLDER ? { accessKey: '' } : {}),
                regionId: undefined,
                regionName: undefined,
              });
              onCredentialFieldChange?.('accessSecret');
            }}
          />
        </InputRow>
        {cloudCredentialLabels?.projectId && (
          <InputRow label={cloudCredentialLabels.projectId}>
            <Input
              value={item.projectId}
              placeholder={t('common.inputTip', '请输入')}
              onChange={(event) => {
                updateItem(index, {
                  projectId: event.target.value,
                  regionId: undefined,
                  regionName: undefined,
                });
                onCredentialFieldChange?.('projectId');
              }}
            />
          </InputRow>
        )}
        <InputRow label={t('Collection.cloudTask.region', '区域')}>
          <div className={styles.credentialInlineControl}>
            <Select
              value={item.regionId}
              onChange={(nextValue, option) => {
                const label = Array.isArray(option) ? option[0]?.label : option?.label;
                updateItem(index, { regionId: nextValue, regionName: typeof label === 'string' ? label : undefined });
              }}
              loading={cloudRegionLoading}
              placeholder={t('common.selectTip', '请选择')}
              options={cloudRegionOptions}
            />
            <Button
              type="text"
              aria-label={t('common.refresh')}
              icon={<SyncOutlined spin={cloudRegionLoading} aria-hidden />}
              onClick={onCloudRegionRefresh}
              className={styles.credentialRefreshButton}
            />
          </div>
        </InputRow>
      </div>
    );
  }

  if (shape === 'influxdb') {
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('Collection.influxdbTask.scheme', '连接协议')}>
          <Select
            value={item.scheme || 'http'}
            options={[
              { label: 'HTTP', value: 'http' },
              { label: 'HTTPS', value: 'https' },
            ]}
            onChange={(scheme) => updateItem(index, { scheme })}
          />
        </InputRow>
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.port}
            onChange={(port) => updateItem(index, { port: port ?? undefined })}
          />
        </InputRow>
        <InputRow
          label={t('Collection.influxdbTask.operatorToken', 'Operator Token')}
          required={false}
        >
          <SecretInput
            value={item.token}
            placeholder={t('Collection.influxdbTask.tokenPlaceholder', '选填，仅完整配置采集需要')}
            editMode={editMode}
            onChange={(token) => updateItem(index, { token })}
          />
        </InputRow>
        <InputRow label={t('Collection.influxdbTask.verifyTls', '校验证书')}>
          <Switch
            disabled={collectModelId === 'smartx'}
            checked={collectModelId === 'smartx' || item.verify_tls !== false}
            onChange={(verify_tls) => updateItem(index, { verify_tls })}
          />
        </InputRow>
        {item.scheme === 'https' && item.verify_tls === false && (
          <Alert
            type="warning"
            showIcon
            message={t(
              'Collection.influxdbTask.tlsWarning',
              '关闭证书校验会增加中间人攻击风险，仅应临时用于受信任网络中的自签名证书。',
            )}
          />
        )}
      </div>
    );
  }

  if (shape === 'platform_api') {
    return (
      <div className={styles.credentialFieldGrid}>
        {item.source !== undefined && (
          <InputRow label={t('Collection.smartxTask.source', '认证来源')}>
            <Input value={item.source} onChange={(event) => updateItem(index, { source: event.target.value })} />
          </InputRow>
        )}
        {item.user_type !== undefined && (
          <InputRow label={t('Collection.fusioncomputeTask.userType', '用户类型')}>
            <Input value={item.user_type} onChange={(event) => updateItem(index, { user_type: event.target.value })} />
          </InputRow>
        )}
        {item.tenant_id !== undefined && (
          <>
            <InputRow label={t('Collection.platformApiTask.tenantId', '租户 ID')}>
              <Input value={item.tenant_id} onChange={(event) => updateItem(index, { tenant_id: event.target.value })} />
            </InputRow>
            <InputRow label={t('Collection.azureTask.subscriptionId', '订阅 ID')}>
              <Input value={item.subscription_id} onChange={(event) => updateItem(index, { subscription_id: event.target.value })} />
            </InputRow>
          </>
        )}
        {item.user_domain_name !== undefined && (
          <>
            <InputRow label={t('Collection.platformApiTask.userDomainName', '用户域名称')}>
              <Input value={item.user_domain_name} onChange={(event) => updateItem(index, { user_domain_name: event.target.value })} />
            </InputRow>
            <InputRow label={t('Collection.platformApiTask.projectId', '项目 ID')} required={false}>
              <Input value={item.project_id} onChange={(event) => updateItem(index, { project_id: event.target.value })} />
            </InputRow>
          </>
        )}

        {item.region !== undefined && (
          <InputRow label={t('Collection.cloudTask.region', '区域')} required={false}>
            <Input value={item.region} onChange={(event) => updateItem(index, { region: event.target.value })} />
          </InputRow>
        )}
        {item.api_version !== undefined && (
          <InputRow label={t('Collection.api_version', 'API 版本')}>
            <Input disabled={collectModelId === 'manageone'} value={item.api_version} onChange={(event) => updateItem(index, { api_version: event.target.value })} />
          </InputRow>
        )}
        {item.scheme !== undefined && (
          <InputRow label={t('Collection.influxdbTask.scheme', '连接协议')}>
            <Select value={item.scheme} options={['http', 'https'].map((value) => ({ label: value.toUpperCase(), value }))}
              onChange={(scheme) => updateItem(index, { scheme })} />
          </InputRow>
        )}

        <InputRow label={item.tenant_id !== undefined ? t('Collection.platformApiTask.clientId', '应用 ID') : t('user', '用户')}>
          <Input
            value={item.username}
            placeholder={t('common.inputTip', '请输入')}
            onChange={(event) => updateItem(index, { username: event.target.value })}
          />
        </InputRow>
        <InputRow label={item.tenant_id !== undefined ? t('Collection.platformApiTask.clientSecret', '客户端密钥') : t('password', '密码')}>
          <SecretInput
            value={item.password}
            placeholder={t('common.inputTip', '请输入')}
            editMode={editMode}
            onChange={(password) => updateItem(index, { password })}
          />
        </InputRow>
        {showPort && <InputRow label={collectModelId === 'openstack' ? t('Collection.platformApiTask.identityPort', '认证服务端口') : t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.port}
            onChange={(port) => updateItem(index, { port: port ?? undefined })}
          />
        </InputRow>}
        {collectModelId !== 'azure' && <InputRow label={t('Collection.influxdbTask.verifyTls', '校验证书')}>
          <Switch
            disabled={collectModelId === 'smartx'}
            checked={collectModelId === 'smartx' || item.verify_tls !== false}
            onChange={(verify_tls) => updateItem(index, { verify_tls })}
          />
        </InputRow>}
        {item.verify_tls === false && (
          <Alert
            type="warning"
            showIcon
            message={t(
              'Collection.platformApiTask.tlsWarning',
              '关闭证书校验会增加中间人攻击风险，仅应临时用于受信任网络中的自签名证书。',
            )}
          />
        )}
      </div>
    );
  }

  return (
    <div className={styles.credentialFieldGrid}>
      {shape === 'network_config_file' && (
        <>
          <InputRow label={t('Collection.credentialPool.transportProtocol', '连接协议')}>
            <Select
              value={normalizeNetworkTransport(item.transport_protocol)}
              options={[
                { label: 'SSH', value: 'ssh' },
                { label: 'Telnet', value: 'telnet' },
              ]}
              onChange={(nextValue) => {
                const transport_protocol = normalizeNetworkTransport(nextValue);
                updateItem(index, {
                  transport_protocol,
                  port: portForNetworkTransportSwitch(item.port, transport_protocol),
                });
              }}
            />
          </InputRow>
          {normalizeNetworkTransport(item.transport_protocol) === 'telnet' && (
            <Alert
              type="warning"
              showIcon
              message={t(
                'Collection.credentialPool.telnetWarning',
                'Telnet 明文传输账号口令，仅应在隔离管理网或设备只开放 TCP/23 时使用。',
              )}
            />
          )}
        </>
      )}
      <InputRow
        label={shape === 'sql' || shape === 'vm' ? t('Collection.VMTask.username', '用户') : t('user', '用户')}
      >
        <Input
          value={shape === 'sql' ? item.user : item.username}
          placeholder={t('common.inputTip', '请输入')}
          onChange={(event) => updateItem(index, shape === 'sql' ? { user: event.target.value } : { username: event.target.value })}
        />
      </InputRow>
      <InputRow
        label={shape === 'sql' || shape === 'vm' ? t('Collection.VMTask.password', '密码') : t('password', '密码')}
      >
        <SecretInput
          value={item.password}
          placeholder={t('common.inputTip', '请输入')}
          editMode={editMode}
          onChange={(nextValue) => updateItem(index, { password: nextValue })}
        />
      </InputRow>
      {showPort && (
        <InputRow label={t('Collection.port', '端口')}>
          <InputNumber
            min={1}
            max={65535}
            className="!w-full"
            value={item.port}
            onChange={(nextValue) => updateItem(index, { port: nextValue ?? undefined })}
          />
        </InputRow>
      )}
      {shape === 'redfish' && (
        <>
          <InputRow label={t('Collection.RedfishTask.verifyTls', '校验证书')}>
            <Switch
              disabled={collectModelId === 'smartx'}
            checked={collectModelId === 'smartx' || item.verify_tls !== false}
              onChange={(verify_tls) => updateItem(index, { verify_tls })}
            />
          </InputRow>
          {item.verify_tls === false && (
            <Alert
              type="warning"
              showIcon
              message={t(
                'Collection.RedfishTask.tlsWarning',
                '关闭证书校验会增加中间人攻击风险，仅应临时用于受信任网络中的自签名证书。',
              )}
            />
          )}
        </>
      )}
      {shape === 'sql' && ['namespace', 'bucket'].filter((key) => item[key] !== undefined).map((key) => (
        <InputRow key={key} label={t(`Collection.${key}`, key)}>
          <Input value={String(item[key] ?? '')} onChange={(event) => updateItem(index, { [key]: event.target.value })} />
        </InputRow>
      ))}
      {shape === 'sql' && showDatabase && (
        <InputRow label={t('Collection.database', '数据库')}>
          <Input
            value={item.database}
            placeholder={t('common.inputTip', '请输入')}
            onChange={(event) => updateItem(index, { database: event.target.value })}
          />
        </InputRow>
      )}
      {shape === 'vm' && (
        <InputRow label={t('Collection.VMTask.sslVerify', 'SSL 验证')}>
          <Switch
            checked={Boolean(item.ssl)}
            onChange={(checked) => updateItem(index, { ssl: checked })}
          />
        </InputRow>
      )}
      {shape === 'network_config_file' && (
        <InputRow label={t('Collection.credentialPool.enablePassword', '特权密码')} required={false}>
          <SecretInput
            value={item.enable_password}
            placeholder={t('common.inputTip', '请输入')}
            editMode={editMode}
            onChange={(nextValue) => updateItem(index, { enable_password: nextValue })}
          />
        </InputRow>
      )}
      {shape === 'ipmi' && (
        <InputRow label={t('Collection.IPMITask.privilege', '权限级别')}>
          <Select
            value={item.privilege || 'administrator'}
            onChange={(nextValue) => updateItem(index, { privilege: nextValue })}
            options={IPMI_PRIVILEGE_OPTIONS}
            placeholder={t('common.selectTip', '请选择')}
          />
        </InputRow>
      )}
    </div>
  );
}

export default function CredentialPoolEditor({
  value = [],
  maxCount = MAX_CREDENTIAL_POOL_SIZE,
  credentialShape,
  onChange,
  editMode = false,
  showDatabase = false,
  showPort = true,
  allowAdd = true,
  allowRemove = true,
  showCount = true,
  cloudRegionOptions = [],
  cloudRegionLoading = false,
  onCloudRegionRefresh,
  onCredentialFieldChange,
  credentialHelp,
  cloudCredentialLabels,
  defaultPort,
  credentialSchema,
  vaultCategory,
  vaultTypeKeys = [],
  collectModelId,
}: CredentialPoolEditorProps): React.ReactElement {
  const { t } = useTranslation();
  const sensors = useSensors(useSensor(PointerSensor));
  const normalizedValue = useMemo(
    () =>
      ensureClientIds(
        credentialShape === 'snmp' ? value.map((item) => withDefaultSnmpVersion(item)) : value
      ),
    [credentialShape, value]
  );
  const [activeKeys, setActiveKeys] = useState<string[]>(
    normalizedValue.length ? [getItemKey(normalizedValue[0], 0)] : []
  );
  const [visibleSecretKeys, setVisibleSecretKeys] = useState<string[]>([]);
  const [helpOpen, setHelpOpen] = useState(false);
  const [credentialNames, setCredentialNames] = useState<Record<string, string>>({});
  const helpContentId = useId();

  const itemKeys = useMemo(
    () => normalizedValue.map((item, index) => getItemKey(item, index)),
    [normalizedValue]
  );

  useEffect(() => {
    if (credentialShape !== 'snmp') {
      return;
    }
    const missingVersion = value.some((item) => !String(item?.version || '').trim());
    if (!missingVersion) {
      return;
    }
    onChange?.(ensureClientIds(value.map((item) => withDefaultSnmpVersion(item))));
  }, [credentialShape, onChange, value]);

  useEffect(() => {
    setActiveKeys((prev) => {
      const filtered = prev.filter((key) => itemKeys.includes(key));
      if (filtered.length) {
        return filtered;
      }
      return itemKeys.length ? [itemKeys[0]] : [];
    });
    setVisibleSecretKeys((prev) => prev.filter((key) => itemKeys.includes(key)));
  }, [itemKeys]);

  const emitChange = (nextItems: CredentialPoolItem[]) => {
    onChange?.(ensureClientIds(nextItems));
  };

  const updateItem = (index: number, patch: Partial<CredentialPoolItem>) => {
    emitChange(
      normalizedValue.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item
      )
    );
  };

  const handleAdd = () => {
    const nextItem = createEmptyCredential(
      credentialShape,
      showDatabase,
      defaultPort,
      credentialSchema,
      showPort,
    );
    if (collectModelId === 'iris') nextItem.namespace = 'USER';
    if (collectModelId === 'couchbase') nextItem.bucket = '';
    const nextItems = [...normalizedValue, nextItem];
    emitChange(nextItems);
    setActiveKeys((prev) => [...prev, getItemKey(nextItem, nextItems.length - 1)]);
  };

  const handleRemove = (index: number) => {
    const nextItems = normalizedValue.filter((_, itemIndex) => itemIndex !== index);
    emitChange(nextItems);
    const removedKey = getItemKey(normalizedValue[index], index);
    setActiveKeys((prev) => prev.filter((key) => key !== removedKey));
    setVisibleSecretKeys((prev) => prev.filter((key) => key !== removedKey));
  };

  const toggleExpanded = (itemKey: string) => {
    setActiveKeys((prev) => (prev.includes(itemKey) ? prev.filter((key) => key !== itemKey) : [...prev, itemKey]));
  };

  const toggleSecretVisible = (itemKey: string) => {
    setVisibleSecretKeys((prev) =>
      prev.includes(itemKey) ? prev.filter((key) => key !== itemKey) : [...prev, itemKey]
    );
  };

  const onDragEnd = (event: CredentialDragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }
    const oldIndex = normalizedValue.findIndex((item, index) => getItemKey(item, index) === active.id);
    const newIndex = normalizedValue.findIndex((item, index) => getItemKey(item, index) === over.id);
    if (oldIndex === -1 || newIndex === -1) {
      return;
    }
    emitChange(arrayMove(normalizedValue, oldIndex, newIndex));
  };

  const sortableEnabled = allowAdd && maxCount > 1;
  const showPoolStrategy = allowAdd && maxCount > 1;
  const helpContent = (
    <div id={helpContentId} className={styles.credentialHelpContent}>
      {credentialHelp ? (
        <>
          <div className={styles.credentialHelpRow}>
            <span>{t('Collection.credentialHelp.labels.protocol', '连接协议')}</span>
            <strong>{credentialHelp.protocol}</strong>
          </div>
          <div className={styles.credentialHelpRow}>
            <span>{t('Collection.credentialHelp.labels.credentialKind', '凭据类型')}</span>
            <strong>{credentialHelp.credentialKind}</strong>
          </div>
          <div className={styles.credentialHelpRow}>
            <span>{t('Collection.credentialHelp.labels.instruction', '填写说明')}</span>
            <strong>{credentialHelp.instruction}</strong>
          </div>
          <div className={styles.credentialHelpRow}>
            <span>{t('Collection.credentialHelp.labels.defaultPort', '默认端口')}</span>
            <strong>{credentialHelp.defaultPort || '—'}</strong>
          </div>
          {credentialHelp.fields?.length ? (
            <div className={styles.credentialFieldHelpSection}>
              <strong>
                {t('Collection.credentialHelp.labels.fieldDetails', '字段说明')}
              </strong>
              <div className={styles.credentialFieldHelpList}>
                {credentialHelp.fields.map((field, index) => (
                  <div
                    className={styles.credentialFieldHelpItem}
                    key={`${field.name}-${index}`}
                  >
                    <div className={styles.credentialFieldHelpHeader}>
                      <strong>{field.name}</strong>
                      <div className={styles.credentialFieldHelpValues}>
                        {field.defaultValue && (
                          <span>
                            {t(
                              'Collection.credentialHelp.labels.defaultValue',
                              '默认',
                            )}
                            ：{field.defaultValue}
                          </span>
                        )}
                        {field.recommendedValue && (
                          <span className={styles.credentialFieldHelpRecommended}>
                            {t(
                              'Collection.credentialHelp.labels.recommendedValue',
                              '推荐',
                            )}
                            ：{field.recommendedValue}
                          </span>
                        )}
                      </div>
                    </div>
                    <span>{field.description}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <div className={styles.credentialHelpFallback}>
          {t(
            'Collection.credentialHelp.unavailableProtocol',
            '此插件尚未提供协议说明，请以插件文档为准。',
          )}
        </div>
      )}
      {showPoolStrategy && (
        <div className={styles.credentialHelpPoolStrategy}>
          <strong>{t('Collection.credentialHelp.labels.poolStrategy', '多凭据策略')}</strong>
          <span>
            {t(
              'Collection.credentialPoolTip',
              '最多配置 3 个凭据，系统按顺序试探，命中后优先复用。',
            )}
          </span>
        </div>
      )}
    </div>
  );

  const renderCredentialCard = (item: CredentialPoolItem, index: number) => {
    const itemKey = getItemKey(item, index);
    const expanded = activeKeys.includes(itemKey);
    const passwordVisible = visibleSecretKeys.includes(itemKey);
    const source = item.credential_source || 'inline';
    // 旧 JOB 引用可能未保存类型；该版本新增 SSH 引用始终显式保存 vault_type_key。
    const legacyPasswordReference = vaultTypeKeys.includes('ssh')
      && ['ssh', 'config_file'].includes(credentialShape)
      && Boolean(item.vault_credential_id)
      && (!item.vault_type_key || item.vault_type_key === 'sql');
    const legacyNetworkReference = credentialShape === 'network_config_file' && vaultTypeKeys.includes('ssh')
      && Boolean(item.vault_credential_id)
      && (!item.vault_type_key || item.vault_type_key === 'platform_api');
    const selectedVaultType = item.vault_type_key || (legacyNetworkReference ? 'platform_api' : legacyPasswordReference ? 'sql' : vaultTypeKeys[0]);
    const previewFields = source === 'vault' ? [] : getPreviewFields(
      item,
      credentialShape,
      t,
      passwordVisible,
      cloudCredentialLabels,
      showPort,
    );

    return (
      <>
        <div className={`${styles.credentialCard} ${expanded ? styles.credentialCardExpanded : ''}`}>
          <div className={styles.credentialCardHeader}>
            <button
              type="button"
              className={`${styles.credentialCardSummary} ${source === 'vault' ? '!flex-1' : ''}`}
              aria-expanded={expanded}
              aria-controls={`credential-panel-${itemKey}`}
              onClick={() => toggleExpanded(itemKey)}
            >
              <div className={source === 'vault' ? 'flex min-w-0 flex-1 items-center gap-2' : styles.credentialTitleBlock}>
                <span className={styles.credentialOrderNumber}>{index + 1}</span>
                <div className={styles.credentialTitle}>{`${t('Collection.credential', '凭据')} ${index + 1}`}</div>
                {source === 'vault' && (
                  <Tooltip title="任务保存凭据引用；执行时读取凭据管理中的认证字段。端口等参数仍在此填写。">
                    <span className="min-w-0 truncate text-xs text-[var(--color-text-secondary)]">
                      {`已有凭据 · ${item.vault_credential_id ? credentialNames[item.vault_credential_id] || '已选择' : '未选择'}`}
                    </span>
                  </Tooltip>
                )}
              </div>
            </button>
            {!expanded && (
              <div className={styles.credentialMetaList}>
                {previewFields.map((field) => (
                  <CredentialMetaField
                    key={field.label}
                    field={field}
                    passwordVisible={passwordVisible}
                    toggleSecretLabel={passwordVisible
                      ? t('Collection.credentialPool.hideSecret', '隐藏凭据')
                      : t('Collection.credentialPool.showSecret', '显示凭据')}
                    onToggleSecret={(event) => {
                      event.stopPropagation();
                      toggleSecretVisible(itemKey);
                    }}
                  />
                ))}
              </div>
            )}
            <div className={styles.credentialActions}>
              {allowRemove && (
                <Tooltip
                  title={normalizedValue.length <= 1
                    ? t('Collection.credentialPool.keepOne', '至少保留 1 个凭据')
                    : t('Collection.credentialPool.remove', '删除凭据')}
                >
                  <Button
                    type="text"
                    danger
                    aria-label={t('Collection.credentialPool.remove', '删除凭据')}
                    icon={<DeleteOutlined aria-hidden="true" />}
                    disabled={normalizedValue.length <= 1}
                    onClick={() => handleRemove(index)}
                  />
                </Tooltip>
              )}
              <Button
                type="text"
                className={styles.credentialExpandButton}
                aria-label={expanded
                  ? t('Collection.credentialPool.collapse', '收起凭据')
                  : t('Collection.credentialPool.expand', '展开凭据')}
                aria-expanded={expanded}
                aria-controls={`credential-panel-${itemKey}`}
                icon={expanded
                  ? <DownOutlined aria-hidden="true" />
                  : <RightOutlined aria-hidden="true" />}
                onClick={() => toggleExpanded(itemKey)}
              />
            </div>
          </div>
          {expanded && (
            <div
              id={`credential-panel-${itemKey}`}
              className={styles.credentialCardBody}
            >
              <div className="mb-3 flex justify-end">
                <Button
                  type="link"
                  className="!px-0"
                  icon={<EditOutlined aria-hidden="true" />}
                  onClick={() => {
                    const next = source === 'vault' ? 'inline' : 'vault';
                    // 首次切到已有凭据时尚未保存类型，仍须保留任务自己的特权密码。
                    const authContext = { ...item, vault_type_key: selectedVaultType };
                    const clean = Object.fromEntries(Object.entries(item).filter(([key]) => !isVaultAuthField(key, authContext) && key !== 'vault_actor_context'));
                    if (next === 'vault') {
                      clean.vault_type_key = selectedVaultType;
                      if (credentialShape === 'network_config_file') {
                        clean.transport_protocol = normalizeNetworkTransport(item.transport_protocol);
                      }
                    }
                    if (next === 'inline') {
                      delete clean.vault_credential_id;
                      delete clean.vault_type_key;
                    }
                    emitChange(normalizedValue.map((candidate, candidateIndex) => candidateIndex === index
                      ? { ...clean, credential_source: next } : candidate));
                  }}
                >
                  {source === 'vault'
                    ? t('Collection.credentialPool.useManual', '改用手动录入')
                    : t('Collection.credentialPool.useExisting', '使用已有凭据')}
                </Button>
              </div>
              {source === 'vault' && (
                <div className="mb-4">
                  {vaultCategory && vaultTypeKeys.length ? (
                    <>
                      {(legacyPasswordReference || legacyNetworkReference) && (
                        <div className="mb-2 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                          <span>{legacyNetworkReference ? t('Collection.legacyNetworkCredentialTip', '当前任务沿用已有的平台账户凭据。') : t('Collection.legacyJobCredentialTip', '当前任务沿用已有的用户名密码凭据。')}</span>
                          <Button type="link" size="small" onClick={() => updateItem(index, {
                            vault_type_key: 'ssh', vault_credential_id: undefined,
                          })}>{t('Collection.switchToSshCredential', '改用 SSH 凭据')}</Button>
                        </div>
                      )}
                      {vaultTypeKeys.length > 1 && (
                        <Select className="mb-2 w-full" value={selectedVaultType}
                          options={vaultTypeKeys.map((key) => ({ label: key, value: key }))}
                          onChange={(vault_type_key) => updateItem(index, { vault_type_key, vault_credential_id: undefined })} />
                      )}
                      <CredentialPicker category={vaultCategory}
                        type={selectedVaultType}
                        value={item.vault_credential_id}
                        onNamesResolved={(credentials) => setCredentialNames((previous) => {
                          const next = { ...previous };
                          let changed = false;
                          credentials.forEach(({ credential_id, name }) => {
                            if (next[credential_id] !== name) {
                              next[credential_id] = name;
                              changed = true;
                            }
                          });
                          return changed ? next : previous;
                        })}
                        onChange={(vault_credential_id) => updateItem(index, {
                          vault_credential_id, vault_type_key: selectedVaultType,
                        })} />
                    </>
                  ) : <Alert type="warning" showIcon message="当前插件没有可用的内置凭据类型" />}
                </div>
              )}
              {source === 'vault' ? renderVaultDynamicFields(
                item, index, credentialShape, updateItem, t, showPort,
                onCloudRegionRefresh, cloudRegionLoading, collectModelId,
                cloudRegionOptions, cloudCredentialLabels,
              ) : renderCredentialFields({
                collectModelId,
                item,
                index,
                shape: credentialShape,
                editMode,
                showDatabase,
                showPort,
                cloudRegionOptions,
                cloudRegionLoading,
                onCloudRegionRefresh,
                onCredentialFieldChange,
                cloudCredentialLabels,
                credentialSchema,
                t,
                updateItem,
              })}
            </div>
          )}
        </div>
      </>
    );
  };

  return (
    <div className={styles.credentialPoolEditor}>
      <div className={styles.credentialPoolHeader}>
        <div className={styles.credentialPoolTitle}>
          <span>{t('Collection.credential', '凭据')}</span>
          <Popover
            content={helpContent}
            trigger="click"
            placement="bottomLeft"
            open={helpOpen}
            onOpenChange={setHelpOpen}
            overlayStyle={{ maxWidth: 'min(520px, calc(100vw - 48px))' }}
          >
            <Button
              type="text"
              size="small"
              className={styles.credentialPoolHelpButton}
              aria-label={t('Collection.credentialHelp.open', '查看凭据填写说明')}
              aria-expanded={helpOpen}
              aria-controls={helpContentId}
              icon={<QuestionCircleOutlined aria-hidden="true" />}
            />
          </Popover>
        </div>
        {allowAdd && (
          <Button
            icon={<PlusOutlined />}
            onClick={handleAdd}
            disabled={normalizedValue.length >= maxCount}
            className={styles.credentialHeaderAddButton}
          >
            {`${t('common.add', '添加')}${t('Collection.credential', '凭据')}`}
          </Button>
        )}
        {!allowAdd && showCount && (
          <div className={styles.credentialPoolCount}>
            <span>{`${normalizedValue.length}/${maxCount}`}</span>
            <span>{t('Collection.credentialPool.configured', '已配置')}</span>
          </div>
        )}
      </div>
      {sortableEnabled ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext
            items={itemKeys}
            strategy={verticalListSortingStrategy}
          >
            <ul className={styles.credentialPoolList}>
              {normalizedValue.map((item, index) => (
                <SortableItem key={getItemKey(item, index)} id={getItemKey(item, index)} index={index}>
                  <HolderOutlined className={styles.credentialDragHandle} />
                  {renderCredentialCard(item, index)}
                </SortableItem>
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      ) : (
        <ul className={styles.credentialPoolList}>
          {normalizedValue.map((item, index) => (
            <li key={getItemKey(item, index)} className={styles.credentialStaticItem}>
              {renderCredentialCard(item, index)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
