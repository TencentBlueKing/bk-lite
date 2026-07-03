'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Input,
  InputNumber,
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
} from '@/app/cmdb/constants/professCollection';
import { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import { useTranslation } from '@/utils/i18n';

import styles from '../index.module.scss';

type CredentialShape = 'ssh' | 'sql' | 'snmp' | 'config_file' | 'network_config_file' | 'vm' | 'cloud' | 'ipmi';

const IPMI_PRIVILEGE_OPTIONS = [
  { label: 'callback', value: 'callback' },
  { label: 'user', value: 'user' },
  { label: 'operator', value: 'operator' },
  { label: 'administrator', value: 'administrator' },
];

export interface CredentialPoolEditorProps {
  value?: CredentialPoolItem[];
  maxCount?: number;
  credentialShape: CredentialShape;
  onChange?: (value: CredentialPoolItem[]) => void;
  editMode?: boolean;
  showDatabase?: boolean;
  allowAdd?: boolean;
  allowRemove?: boolean;
  showCount?: boolean;
  cloudRegionOptions?: { label: string; value: string }[];
  cloudRegionLoading?: boolean;
  onCloudRegionRefresh?: () => void;
  onCredentialFieldChange?: (field: string) => void;
}

const makeClientId = () => `cred-local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;

const ensureClientIds = (items: CredentialPoolItem[]) =>
  items.map((item) => ({
    ...item,
    _client_id: item._client_id || makeClientId(),
  }));

const createEmptyCredential = (shape: CredentialShape, showDatabase?: boolean): CredentialPoolItem => {
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

  return {
    _client_id: makeClientId(),
    port: shape === 'sql' ? (showDatabase ? '1433' : '3306') : shape === 'vm' ? '443' : '22',
    ...(shape === 'vm' ? { ssl: false } : {}),
    ...(shape === 'cloud' ? { accessKey: '', accessSecret: '', regionId: '' } : {}),
    ...(shape === 'ipmi' ? { port: '623', privilege: 'administrator' } : {}),
    ...(shape === 'sql' && showDatabase ? { database: 'master' } : {}),
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
  passwordVisible: boolean
) {
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
    return [
      { label: t('Collection.cloudTask.accessKey', '秘匙'), value: item.accessKey || '--' },
      {
        label: t('Collection.cloudTask.accessSecret', '秘钥'),
        value: passwordVisible && item.accessSecret && item.accessSecret !== PASSWORD_PLACEHOLDER
          ? item.accessSecret
          : getMaskedSecret(item.accessSecret),
        isSecret: true,
      },
      { label: t('Collection.cloudTask.region', '区域'), value: item.regionName || item.regionId || '--' },
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
    { label: t('Collection.port', '端口'), value: String(item.port || (shape === 'sql' ? '3306' : shape === 'vm' ? '443' : shape === 'ipmi' ? '623' : '22')) },
  ];
  if (shape === 'network_config_file') {
    fields.push({
      label: '特权密码',
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
}: {
  field: { label: string; value: string; isSecret?: boolean };
  passwordVisible: boolean;
  onToggleSecret: (event: React.MouseEvent<HTMLElement>) => void;
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
          icon={passwordVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
          onClick={onToggleSecret}
        />
      )}
    </div>
  );
}

function SecretInput({
  value,
  placeholder,
  editMode,
  onChange,
}: {
  value?: string;
  placeholder: string;
  editMode: boolean;
  onChange: (nextValue: string) => void;
}) {
  return (
    <Input.Password
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
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <div className={styles.credentialFieldRow}>
      <div className={styles.credentialFieldLabel}>
        {required && <span className={styles.credentialRequiredMark}>*</span>}
        <span>{label}</span>
      </div>
      <div className={styles.credentialFieldControl}>{children}</div>
    </div>
  );
}

function renderCredentialFields({
  item,
  index,
  shape,
  editMode,
  showDatabase,
  cloudRegionOptions,
  cloudRegionLoading,
  onCloudRegionRefresh,
  onCredentialFieldChange,
  t,
  updateItem,
}: {
  item: CredentialPoolItem;
  index: number;
  shape: CredentialShape;
  editMode: boolean;
  showDatabase: boolean;
  cloudRegionOptions: { label: string; value: string }[];
  cloudRegionLoading: boolean;
  onCloudRegionRefresh?: () => void;
  onCredentialFieldChange?: (field: string) => void;
  t: (key: string, defaultMessage?: string) => string;
  updateItem: (index: number, patch: Partial<CredentialPoolItem>) => void;
}) {
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
            className="w-32"
            value={item.snmp_port as any}
            onChange={(nextValue) => updateItem(index, { snmp_port: nextValue as any })}
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
              <Select value={item.integrity || 'sha'} onChange={(nextValue) => updateItem(index, { integrity: nextValue })}>
                <Select.Option value="sha">SHA</Select.Option>
                <Select.Option value="md5">MD5</Select.Option>
              </Select>
            </InputRow>
            {level === 'authPriv' && (
              <>
                <InputRow label={t('Collection.SNMPTask.encryptAlgorithm', '加密算法')}>
                  <Select value={item.privacy || 'aes'} onChange={(nextValue) => updateItem(index, { privacy: nextValue })}>
                    <Select.Option value="aes">AES</Select.Option>
                    <Select.Option value="des">DES</Select.Option>
                  </Select>
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

  if (shape === 'cloud') {
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('Collection.cloudTask.accessKey', '秘匙')}>
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
        <InputRow label={t('Collection.cloudTask.accessSecret', '秘钥')}>
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
              icon={<SyncOutlined spin={cloudRegionLoading} />}
              onClick={onCloudRegionRefresh}
              className={styles.credentialRefreshButton}
            />
          </div>
        </InputRow>
      </div>
    );
  }

  return (
    <div className={styles.credentialFieldGrid}>
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
      <InputRow label={t('Collection.port', '端口')}>
        <InputNumber
          min={1}
          max={65535}
          className="w-32"
          value={item.port as any}
          onChange={(nextValue) => updateItem(index, { port: nextValue as any })}
        />
      </InputRow>
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
        <InputRow label="特权密码" required={false}>
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
  allowAdd = true,
  allowRemove = true,
  showCount = true,
  cloudRegionOptions = [],
  cloudRegionLoading = false,
  onCloudRegionRefresh,
  onCredentialFieldChange,
}: CredentialPoolEditorProps): JSX.Element {
  const { t } = useTranslation();
  const sensors = useSensors(useSensor(PointerSensor));
  const normalizedValue = useMemo(() => ensureClientIds(value), [value]);
  const [activeKeys, setActiveKeys] = useState<string[]>(
    normalizedValue.length ? [getItemKey(normalizedValue[0], 0)] : []
  );
  const [visibleSecretKeys, setVisibleSecretKeys] = useState<string[]>([]);

  const itemKeys = useMemo(
    () => normalizedValue.map((item, index) => getItemKey(item, index)),
    [normalizedValue]
  );

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
    const nextItem = createEmptyCredential(credentialShape, showDatabase);
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

  const onDragEnd = (event: any) => {
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

  const renderCredentialCard = (item: CredentialPoolItem, index: number) => {
    const itemKey = getItemKey(item, index);
    const expanded = activeKeys.includes(itemKey);
    const passwordVisible = visibleSecretKeys.includes(itemKey);
    const previewFields = getPreviewFields(item, credentialShape, t, passwordVisible);

    return (
      <>
        <span className={styles.credentialOrderNumber}>{index + 1}</span>
        <div className={`${styles.credentialCard} ${expanded ? styles.credentialCardExpanded : ''}`}>
          <div className={styles.credentialCardHeader}>
            <div className={styles.credentialCardSummary} onClick={() => toggleExpanded(itemKey)}>
              <div className={styles.credentialTitleBlock}>
                <div className={styles.credentialTitle}>{`${t('Collection.credential', '凭据')} ${index + 1}`}</div>
              </div>
              {!expanded && (
                <div className={styles.credentialMetaList}>
                  {previewFields.map((field) => (
                    <CredentialMetaField
                      key={field.label}
                      field={field}
                      passwordVisible={passwordVisible}
                      onToggleSecret={(event) => {
                        event.stopPropagation();
                        toggleSecretVisible(itemKey);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
            <div className={styles.credentialActions}>
              {allowRemove && (
                <Tooltip title={normalizedValue.length <= 1 ? '至少保留 1 个凭据' : '删除凭据'}>
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    disabled={normalizedValue.length <= 1}
                    onClick={() => handleRemove(index)}
                  />
                </Tooltip>
              )}
              <Button
                type="text"
                className={styles.credentialExpandButton}
                icon={expanded ? <DownOutlined /> : <RightOutlined />}
                onClick={() => toggleExpanded(itemKey)}
              />
            </div>
          </div>
          {expanded && (
            <div className={styles.credentialCardBody}>
              {renderCredentialFields({
                item,
                index,
                shape: credentialShape,
                editMode,
                showDatabase,
                cloudRegionOptions,
                cloudRegionLoading,
                onCloudRegionRefresh,
                onCredentialFieldChange,
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
          <Tooltip title={t('Collection.credentialPoolTip', '最多配置 3 个凭据，系统按顺序试探，命中后优先复用。')}>
            <QuestionCircleOutlined className={styles.credentialPoolHelpIcon} />
          </Tooltip>
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
        {!allowAdd && showCount && <div className={styles.credentialPoolCount}>{`${normalizedValue.length}/${maxCount}`}</div>}
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
