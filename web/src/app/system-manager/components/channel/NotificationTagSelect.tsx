'use client';

import React, { useMemo, useState } from 'react';
import { Cascader, Input, Modal, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

const { SHOW_CHILD } = Cascader;
const FORBIDDEN = /[: \n\r,]/;
const MAX_LENGTH = 64;

export interface NotificationTagOption {
  key: string;
  value: string;
}

interface NotificationTagSelectProps {
  options?: NotificationTagOption[];
  value?: string[];
  onChange?: (value: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

const parsePairs = (value?: string[]) => {
  const raw = Array.isArray(value) ? value : [];
  return raw
    .filter((item) => typeof item === 'string' && item.split(':').length === 2)
    .map((item) => {
      const [key, tagValue] = item.split(':');
      return { key: (key || '').trim(), value: (tagValue || '').trim() };
    })
    .filter((item) => item.key && item.value);
};

const NotificationTagSelect: React.FC<NotificationTagSelectProps> = ({
  options = [],
  value,
  onChange,
  disabled,
  placeholder,
}) => {
  const { t } = useTranslation();
  const [customKey, setCustomKey] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [tagModalVisible, setTagModalVisible] = useState(false);
  const selectedPairs = useMemo(() => parsePairs(value), [value]);

  const cascaderOptions = useMemo(() => {
    const grouped = new Map<string, string[]>();
    const add = (key: string, tagValue: string) => {
      const values = grouped.get(key) || [];
      if (!values.includes(tagValue)) {
        values.push(tagValue);
      }
      grouped.set(key, values);
    };
    options.forEach((item) => {
      const key = (item?.key || '').trim();
      const tagValue = (item?.value || '').trim();
      if (key && tagValue) {
        add(key, tagValue);
      }
    });
    selectedPairs.forEach((item) => add(item.key, item.value));
    return Array.from(grouped.entries()).map(([key, values]) => ({
      value: key,
      label: key,
      children: values.map((tagValue) => ({ value: tagValue, label: tagValue })),
    }));
  }, [options, selectedPairs]);

  const emitPairs = (pairs: Array<{ key: string; value: string }>) => {
    const unique: string[] = [];
    pairs.forEach((item) => {
      const key = (item.key || '').trim();
      const tagValue = (item.value || '').trim();
      const token = `${key}:${tagValue}`;
      if (key && tagValue && !unique.includes(token)) {
        unique.push(token);
      }
    });
    onChange?.(unique);
  };

  const handleAddCustom = () => {
    const key = customKey.trim();
    const tagValue = customValue.trim();
    if (!key || !tagValue) {
      message.warning(t('common.required'));
      return;
    }
    if (
      key.length > MAX_LENGTH
      || tagValue.length > MAX_LENGTH
      || FORBIDDEN.test(key)
      || FORBIDDEN.test(tagValue)
    ) {
      message.warning(t('system.channel.settings.tagFormatError'));
      return;
    }
    emitPairs([...selectedPairs, { key, value: tagValue }]);
    setCustomKey('');
    setCustomValue('');
    setTagModalVisible(false);
  };

  return (
    <div className="flex items-center gap-2">
      <Cascader
        multiple
        showSearch
        showCheckedStrategy={SHOW_CHILD}
        maxTagCount="responsive"
        disabled={disabled}
        options={cascaderOptions}
        value={selectedPairs.map((item) => [item.key, item.value])}
        onChange={(paths) => {
          const pairs = (paths || [])
            .filter((path) => Array.isArray(path) && path.length >= 2)
            .map((path) => ({ key: String(path[0]), value: String(path[1]) }));
          emitPairs(pairs);
        }}
        displayRender={(labels) => labels.join(':')}
        placeholder={placeholder}
        className="min-w-0 flex-1"
      />
      {!disabled && (
        <button
          type="button"
          aria-label={t('common.add')}
          className="flex h-8 w-8 items-center justify-center rounded border border-dashed border-[var(--color-border-2)] text-[var(--color-text-3)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
          onClick={() => {
            setCustomKey('');
            setCustomValue('');
            setTagModalVisible(true);
          }}
        >
          <PlusOutlined />
        </button>
      )}
      <Modal
        title={t('common.add')}
        open={tagModalVisible}
        onOk={handleAddCustom}
        onCancel={() => {
          setTagModalVisible(false);
          setCustomKey('');
          setCustomValue('');
        }}
        destroyOnHidden
        centered
        width={400}
      >
        <div className="flex items-center gap-3 py-4">
          <Input
            value={customKey}
            onChange={(event) => setCustomKey(event.target.value)}
            placeholder="key"
            maxLength={MAX_LENGTH}
          />
          <Input
            value={customValue}
            onChange={(event) => setCustomValue(event.target.value)}
            placeholder="value"
            maxLength={MAX_LENGTH}
          />
        </div>
      </Modal>
    </div>
  );
};

export default NotificationTagSelect;
