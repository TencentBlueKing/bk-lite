import React, { useState, useMemo } from 'react';
import { Cascader, Input, Modal, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { TagAttrOption } from '@/app/cmdb/types/assetManage';

const { SHOW_CHILD } = Cascader;

interface TagCascaderEditorProps {
  option?: TagAttrOption;
  value?: string[];
  onChange?: (value: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

const TagCascaderEditor: React.FC<TagCascaderEditorProps> = ({
  option,
  value,
  onChange,
  disabled,
  placeholder,
}) => {
  const { t } = useTranslation();
  const [customKey, setCustomKey] = useState('');
  const [customValue, setCustomValue] = useState('');
  const [tagModalVisible, setTagModalVisible] = useState(false);

  const mode = option?.mode || 'free';
  const isFreeMode = mode === 'free';
  const configured = Array.isArray(option?.options) ? option!.options : [];

  const selectedPairs = useMemo(() => {
    const raw = Array.isArray(value) ? value : [];
    return raw
      .filter((item) => typeof item === 'string' && item.includes(':'))
      .map((item) => {
        const [key, ...rest] = item.split(':');
        return { key: (key || '').trim(), value: rest.join(':').trim() };
      })
      .filter((item) => item.key && item.value);
  }, [value]);

  const knownOptionsRef = React.useRef<Record<string, Set<string>>>({});

  const cascaderOptions = useMemo(() => {
    const map = knownOptionsRef.current;
    configured.forEach((item) => {
      const key = (item?.key || '').trim();
      const val = (item?.value || '').trim();
      if (!key || !val) return;
      if (!map[key]) map[key] = new Set<string>();
      map[key].add(val);
    });
    if (isFreeMode) {
      selectedPairs.forEach((item) => {
        if (!map[item.key]) map[item.key] = new Set<string>();
        map[item.key].add(item.value);
      });
    }
    const keys = Object.keys(map).sort();
    return keys.map((key) => ({
      value: key,
      label: key,
      children: Array.from(map[key]).sort().map((val) => ({
        value: val,
        label: val,
      })),
    }));
  }, [configured, selectedPairs, isFreeMode]);

  const cascaderValue = useMemo<string[][]>(() => {
    return selectedPairs.map((item) => [item.key, item.value]);
  }, [selectedPairs]);

  const emitPairs = (pairs: Array<{ key: string; value: string }>) => {
    const unique = new Set<string>();
    pairs.forEach((item) => {
      const key = (item.key || '').trim();
      const val = (item.value || '').trim();
      if (!key || !val) return;
      unique.add(`${key}:${val}`);
    });
    onChange?.(Array.from(unique));
  };

  const handleCascaderChange = (paths: string[][]) => {
    const pairs = (paths || [])
      .filter((path) => Array.isArray(path) && path.length >= 2)
      .map((path) => ({ key: String(path[0]), value: String(path[1]) }));
    emitPairs(pairs);
  };

  const handleAddCustom = () => {
    const key = customKey.trim();
    const val = customValue.trim();
    if (!key || !val) {
      message.warning(t('required'));
      return;
    }
    if (/[:\n\r]/.test(key) || /[:\n\r]/.test(val)) {
      message.warning(t('Model.tagBatchFormatError'));
      return;
    }
    emitPairs([...selectedPairs, { key, value: val }]);
    setCustomKey('');
    setCustomValue('');
    setTagModalVisible(false);
  };

  const openTagModal = () => {
    setCustomKey('');
    setCustomValue('');
    setTagModalVisible(true);
  };

  const closeTagModal = () => {
    setTagModalVisible(false);
    setCustomKey('');
    setCustomValue('');
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
        value={cascaderValue}
        onChange={handleCascaderChange}
        displayRender={(labels) => labels.join(':')}
        placeholder={placeholder}
        style={{ flex: 1 }}
      />
      {isFreeMode && !disabled && (
        <div
          className="flex items-center justify-center w-8 h-8 border border-dashed border-[var(--color-border-2)] rounded cursor-pointer hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
          onClick={openTagModal}
        >
          <PlusOutlined className="text-[var(--color-text-3)]" />
        </div>
      )}
      <Modal
        title={t('common.add')}
        open={tagModalVisible}
        onOk={handleAddCustom}
        onCancel={closeTagModal}
        destroyOnHidden
        centered
        width={400}
      >
        <div className="flex items-center gap-3 py-4">
          <Input
            value={customKey}
            onChange={(e) => setCustomKey(e.target.value)}
            placeholder="key"
          />
          <Input
            value={customValue}
            onChange={(e) => setCustomValue(e.target.value)}
            placeholder="value"
          />
        </div>
      </Modal>
    </div>
  );
};

export default TagCascaderEditor;
