'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Input,
  InputNumber,
  Select,
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
  RightOutlined,
} from '@ant-design/icons';

import SortableItem from '@/app/cmdb/components/sortable-item';
import {
  MAX_CREDENTIAL_POOL_SIZE,
  PASSWORD_PLACEHOLDER,
} from '@/app/cmdb/constants/professCollection';
import { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import { useTranslation } from '@/utils/i18n';

import styles from '../index.module.scss';

type CredentialShape = 'ssh' | 'sql' | 'snmp' | 'config_file';

export interface CredentialPoolEditorProps {
  value?: CredentialPoolItem[];
  maxCount?: number;
  credentialShape: CredentialShape;
  onChange?: (value: CredentialPoolItem[]) => void;
  editMode?: boolean;
  showDatabase?: boolean;
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
    port: shape === 'sql' ? (showDatabase ? '1433' : '3306') : '22',
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
  t: (key: string) => string,
  passwordVisible: boolean
) {
  if (shape === 'snmp') {
    const secretValue = item.version === 'v3' ? item.authkey : item.community;
    return [
      { label: t('Collection.SNMPTask.version'), value: item.version || 'v2' },
      {
        label: item.version === 'v3' ? t('Collection.SNMPTask.userName') : t('Collection.SNMPTask.communityString'),
        value: item.version === 'v3' ? item.username || '--' : passwordVisible ? secretValue || '--' : getMaskedSecret(secretValue),
        isSecret: item.version !== 'v3',
      },
      { label: t('Collection.port'), value: String(item.snmp_port || 161) },
    ];
  }

  const username = shape === 'sql' ? item.user : item.username;
  return [
    { label: shape === 'sql' ? t('Collection.VMTask.username') : t('user'), value: username || '--' },
    {
      label: shape === 'sql' ? t('Collection.VMTask.password') : t('password'),
      value: passwordVisible && item.password && item.password !== PASSWORD_PLACEHOLDER ? item.password : getMaskedSecret(item.password),
      isSecret: true,
    },
    { label: t('Collection.port'), value: String(item.port || (shape === 'sql' ? '3306' : '22')) },
  ];
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

function InputRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.credentialFieldRow}>
      <div className={styles.credentialFieldLabel}>{label}</div>
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
  t,
  updateItem,
}: {
  item: CredentialPoolItem;
  index: number;
  shape: CredentialShape;
  editMode: boolean;
  showDatabase: boolean;
  t: (key: string) => string;
  updateItem: (index: number, patch: Partial<CredentialPoolItem>) => void;
}) {
  if (shape === 'snmp') {
    const version = item.version || 'v2';
    const level = item.level || 'authNoPriv';
    return (
      <div className={styles.credentialFieldGrid}>
        <InputRow label={t('Collection.SNMPTask.version')}>
          <Select value={version} onChange={(nextValue) => updateItem(index, { version: nextValue })}>
            <Select.Option value="v2">V2</Select.Option>
            <Select.Option value="v2c">V2C</Select.Option>
            <Select.Option value="v3">V3</Select.Option>
          </Select>
        </InputRow>
        <InputRow label={t('Collection.port')}>
          <InputNumber
            min={1}
            max={65535}
            className="w-32"
            value={item.snmp_port as any}
            onChange={(nextValue) => updateItem(index, { snmp_port: nextValue as any })}
          />
        </InputRow>

        {version !== 'v3' ? (
          <InputRow label={t('Collection.SNMPTask.communityString')}>
            <SecretInput
              value={item.community}
              placeholder={t('common.inputTip')}
              editMode={editMode}
              onChange={(nextValue) => updateItem(index, { community: nextValue })}
            />
          </InputRow>
        ) : (
          <>
            <InputRow label={t('Collection.SNMPTask.securityLevel')}>
              <Select value={level} onChange={(nextValue) => updateItem(index, { level: nextValue })}>
                <Select.Option value="authNoPriv">认证不加密</Select.Option>
                <Select.Option value="authPriv">认证加密</Select.Option>
              </Select>
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.userName')}>
              <Input
                value={item.username}
                placeholder={t('common.inputTip')}
                onChange={(event) => updateItem(index, { username: event.target.value })}
              />
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.authPassword')}>
              <SecretInput
                value={item.authkey}
                placeholder={t('common.inputTip')}
                editMode={editMode}
                onChange={(nextValue) => updateItem(index, { authkey: nextValue })}
              />
            </InputRow>
            <InputRow label={t('Collection.SNMPTask.hashAlgorithm')}>
              <Select value={item.integrity || 'sha'} onChange={(nextValue) => updateItem(index, { integrity: nextValue })}>
                <Select.Option value="sha">SHA</Select.Option>
                <Select.Option value="md5">MD5</Select.Option>
              </Select>
            </InputRow>
            {level === 'authPriv' && (
              <>
                <InputRow label={t('Collection.SNMPTask.encryptAlgorithm')}>
                  <Select value={item.privacy || 'aes'} onChange={(nextValue) => updateItem(index, { privacy: nextValue })}>
                    <Select.Option value="aes">AES</Select.Option>
                    <Select.Option value="des">DES</Select.Option>
                  </Select>
                </InputRow>
                <InputRow label={t('Collection.SNMPTask.encryptKey')}>
                  <SecretInput
                    value={item.privkey}
                    placeholder={t('common.inputTip')}
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

  return (
    <div className={styles.credentialFieldGrid}>
      <InputRow label={shape === 'sql' ? t('Collection.VMTask.username') : t('user')}>
        <Input
          value={shape === 'sql' ? item.user : item.username}
          placeholder={t('common.inputTip')}
          onChange={(event) => updateItem(index, shape === 'sql' ? { user: event.target.value } : { username: event.target.value })}
        />
      </InputRow>
      <InputRow label={shape === 'sql' ? t('Collection.VMTask.password') : t('password')}>
        <SecretInput
          value={item.password}
          placeholder={t('common.inputTip')}
          editMode={editMode}
          onChange={(nextValue) => updateItem(index, { password: nextValue })}
        />
      </InputRow>
      <InputRow label={t('Collection.port')}>
        <InputNumber
          min={1}
          max={65535}
          className="w-32"
          value={item.port as any}
          onChange={(nextValue) => updateItem(index, { port: nextValue as any })}
        />
      </InputRow>
      {shape === 'sql' && showDatabase && (
        <InputRow label={t('Collection.database')}>
          <Input
            value={item.database}
            placeholder={t('common.inputTip')}
            onChange={(event) => updateItem(index, { database: event.target.value })}
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

  return (
    <div className={styles.credentialPoolEditor}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext
          items={itemKeys}
          strategy={verticalListSortingStrategy}
        >
          <ul className={styles.credentialPoolList}>
            {normalizedValue.map((item, index) => {
              const itemKey = getItemKey(item, index);
              const expanded = activeKeys.includes(itemKey);
              const passwordVisible = visibleSecretKeys.includes(itemKey);
              const previewFields = getPreviewFields(item, credentialShape, t, passwordVisible);
              return (
                <SortableItem key={itemKey} id={itemKey} index={index}>
                  <HolderOutlined className={styles.credentialDragHandle} />
                  <div className={`${styles.credentialCard} ${expanded ? styles.credentialCardExpanded : ''}`}>
                    <div className={styles.credentialCardHeader}>
                      <div className={styles.credentialCardSummary} onClick={() => toggleExpanded(itemKey)}>
                        <div className={styles.credentialTitle}>{`${t('Collection.credential')} ${index + 1}`}</div>
                        <div className={styles.credentialMetaList}>
                          {previewFields.map((field) => (
                            <div key={field.label} className={styles.credentialMetaItem}>
                              <span className={styles.credentialMetaLabel}>{field.label}:</span>
                              <span className={styles.credentialMetaValue}>{field.value}</span>
                              {field.isSecret && (
                                <Button
                                  type="text"
                                  size="small"
                                  className={styles.credentialMetaToggle}
                                  icon={passwordVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    toggleSecretVisible(itemKey);
                                  }}
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className={styles.credentialActions}>
                        <Button
                          type="text"
                          icon={<EditOutlined />}
                          onClick={() => setActiveKeys((prev) => (prev.includes(itemKey) ? prev : [...prev, itemKey]))}
                        />
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          disabled={normalizedValue.length <= 1}
                          onClick={() => handleRemove(index)}
                        />
                        <Button
                          type="text"
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
                          t,
                          updateItem,
                        })}
                      </div>
                    )}
                  </div>
                </SortableItem>
              );
            })}
          </ul>
        </SortableContext>
      </DndContext>
      <div className={styles.credentialPoolFooter}>
        <Button
          icon={<PlusOutlined />}
          onClick={handleAdd}
          disabled={normalizedValue.length >= maxCount}
          className={styles.credentialAddButton}
        >
          {`${t('common.add')}${t('Collection.credential')}`}
        </Button>
        <div className={styles.credentialPoolHint}>{`最多可配置 ${maxCount} 个凭据，按顺序依次试探`}</div>
      </div>
    </div>
  );
}