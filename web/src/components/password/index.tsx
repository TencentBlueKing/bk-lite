import React, { useEffect, useRef, useState } from 'react';
import { Input, Button, Tooltip } from 'antd';
import {
  CopyOutlined,
  EditOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useCopy } from '@/hooks/useCopy';
import { useTranslation } from '@/utils/i18n';
import { normalizePasswordWhitespace } from './normalizePasswordWhitespace';

interface PasswordProps {
  style?: Record<string, string | number>;
  className?: string;
  placeholder?: string;
  value?: string;
  allowCopy?: boolean; // 是否显示复制图标
  clickToEdit?: boolean; // 是否需要点击编辑图标才能编辑,默认true
  disabled?: boolean;
  status?: '' | 'warning' | 'error';
  trimOuterWhitespace?: boolean;
  trimmedHintMode?: 'text' | 'tooltip';
  onChange?: (value: string) => void;
  onCopy?: (value: string) => void;
  onReset?: () => void;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  onPaste?: (event: React.ClipboardEvent<HTMLInputElement>) => void;
}

const Password: React.FC<PasswordProps> = ({
  style = {},
  className = 'w-full',
  placeholder = '',
  value = '',
  allowCopy = false,
  clickToEdit = true,
  disabled = false,
  status,
  trimOuterWhitespace = false,
  trimmedHintMode = 'text',
  onChange,
  onCopy,
  onReset,
  onBlur,
  onPaste,
}) => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const [password, setPassword] = useState<string>('');
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [showTrimmedHint, setShowTrimmedHint] = useState<boolean>(false);
  const pastePendingRef = useRef(false);

  useEffect(() => {
    setPassword(value);
  }, [value]);

  const handleEdit = () => {
    setPassword('');
    setIsEditing(true);
    setShowTrimmedHint(false);
    onChange?.('');
    onReset?.();
  };

  const updatePassword = (nextValue: string, normalizeWhitespace: boolean) => {
    const result = normalizeWhitespace
      ? normalizePasswordWhitespace(nextValue)
      : { value: nextValue, changed: false };
    setPassword(result.value);
    setShowTrimmedHint(result.changed);
    onChange?.(result.value);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    const pasted = pastePendingRef.current;
    pastePendingRef.current = false;
    updatePassword(newValue, trimOuterWhitespace && pasted);
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    pastePendingRef.current = true;
    queueMicrotask(() => {
      pastePendingRef.current = false;
    });
    onPaste?.(event);
  };

  const handleBlur = (event: React.FocusEvent<HTMLInputElement>) => {
    if (trimOuterWhitespace) {
      const result = normalizePasswordWhitespace(password);
      if (result.changed) {
        setPassword(result.value);
        setShowTrimmedHint(true);
        onChange?.(result.value);
      }
    }
    onBlur?.(event);
  };

  const copyPassword = () => {
    if (onCopy) {
      onCopy(password);
      return;
    }
    copy(value);
  };

  const isEditable = !clickToEdit || isEditing;

  if (isEditable) {
    return (
      <>
        <Input.Password
          className={className}
          style={style}
          value={password}
          disabled={disabled}
          status={status}
          allowClear={!disabled}
          visibilityToggle={!disabled}
          placeholder={placeholder || t('common.inputPassword')}
          autoComplete="new-password"
          onChange={handleChange}
          onPaste={handlePaste}
          onBlur={handleBlur}
        />
        {showTrimmedHint && trimmedHintMode === 'text' && (
          <span
            aria-live="polite"
            className="text-[12px] leading-[18px] text-[var(--theme-color-status-warning)]"
          >
            {t('common.passwordWhitespaceTrimmed')}
          </span>
        )}
        {showTrimmedHint && trimmedHintMode === 'tooltip' && (
          <Tooltip title={t('common.passwordWhitespaceTrimmed')}>
            <InfoCircleOutlined
              aria-label={t('common.passwordWhitespaceTrimmed')}
              className="shrink-0 text-[var(--theme-color-status-warning)]"
            />
          </Tooltip>
        )}
      </>
    );
  }

  return (
    <Input
      className={className}
      style={style}
      type="password"
      value={password}
      disabled
      status={status}
      placeholder={placeholder || t('common.inputPassword')}
      autoComplete="new-password"
      suffix={
        <div className="flex items-center">
          {clickToEdit && (
            <Tooltip title={t('common.edit')}>
              <Button
                size="small"
                type="link"
                icon={<EditOutlined />}
                disabled={disabled}
                onClick={handleEdit}
              />
            </Tooltip>
          )}
          {allowCopy && (
            <Tooltip title={t('common.copy')}>
              <Button
                size="small"
                type="link"
                icon={<CopyOutlined />}
                disabled={!password}
                onClick={copyPassword}
              />
            </Tooltip>
          )}
        </div>
      }
      onChange={handleChange}
    />
  );
};

export default Password;
export {
  normalizePasswordFields,
  normalizePasswordWhitespace,
} from './normalizePasswordWhitespace';
