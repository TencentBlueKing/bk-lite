'use client';

import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {Input, message as antMessage, Select} from 'antd';
import {ClockCircleOutlined} from '@ant-design/icons';
import {useTranslation} from '@/utils/i18n';
import {UserChoiceOption, UserChoiceRequest} from '@/app/opspilot/types/global';

interface UserChoiceCardProps {
  request: UserChoiceRequest;
  token: string;
  onSubmit: (choiceId: string, status: 'submitted' | 'timeout', selected: string[]) => void;
}

const UserChoiceCard: React.FC<UserChoiceCardProps> = ({ request, token, onSubmit }) => {
  const { t } = useTranslation();
  const a2uiComponent = request.a2ui?.component || 'user-choice';
  const a2uiVersion = request.a2ui?.version || 'legacy';
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [textInput, setTextInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const elapsed = (Date.now() - request.received_at) / 1000;
    return Math.max(0, Math.floor(request.timeout_seconds - elapsed));
  });

  const displayMode = useMemo(() => {
    if (request.display_hint === 'text') return 'text';
    if (request.options.length === 0) return 'text';
    if (request.multiple) return 'checkbox';
    if (request.display_hint !== 'auto') return request.display_hint;
    return request.options.length <= 8 ? 'buttons' : 'dropdown';
  }, [request.multiple, request.display_hint, request.options.length]);

  useEffect(() => {
    if (request.status !== 'pending') return;
    const timer = setInterval(() => {
      const elapsed = (Date.now() - request.received_at) / 1000;
      const remaining = Math.max(0, Math.floor(request.timeout_seconds - elapsed));
      setRemainingSeconds(remaining);
      if (remaining <= 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [request.received_at, request.timeout_seconds, request.status]);

  const handleSubmit = useCallback(async (keys: string[]) => {
    if (keys.length < request.min_select) {
      antMessage.warning(t('chat.choiceMinSelect', undefined, { min: request.min_select }));
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch('/api/proxy/opspilot/bot_mgmt/submit_choice/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          execution_id: request.execution_id,
          node_id: request.node_id,
          choice_id: request.choice_id,
          selected: keys,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      onSubmit(request.choice_id, 'submitted', keys);
    } catch {
      antMessage.error(t('chat.choiceSubmitFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [token, request, onSubmit, t]);

  const handleButtonClick = useCallback((key: string) => {
    handleSubmit([key]);
  }, [handleSubmit]);

  const handleConfirm = useCallback(() => {
    handleSubmit(selectedKeys);
  }, [handleSubmit, selectedKeys]);

  const handleCheckboxChange = useCallback((key: string) => {
    setSelectedKeys(prev => {
      if (prev.includes(key)) return prev.filter(k => k !== key);
      if (request.max_select > 0 && prev.length >= request.max_select) {
        antMessage.warning(t('chat.choiceMaxSelect', undefined, { max: request.max_select }));
        return prev;
      }
      return [...prev, key];
    });
  }, [request.max_select, t]);

  const handleDropdownChange = useCallback((value: string) => {
    handleSubmit([value]);
  }, [handleSubmit]);

  const handleTextSubmit = useCallback(() => {
    if (!textInput.trim()) return;
    handleSubmit([textInput.trim()]);
  }, [handleSubmit, textInput]);

  const isTimedOut = remainingSeconds <= 0 && request.status === 'pending';
  const isPending = request.status === 'pending' && !isTimedOut;
  const isCompleted = request.status === 'submitted' || request.status === 'timeout' || isTimedOut;

  // Completed: don't render standalone row — result is shown inline in tool call panel
  if (isCompleted) {
    return null;
  }

  const renderOptionCard = (option: UserChoiceOption, isSelected: boolean, onClick: () => void) => (
    <button
      key={option.key}
      type="button"
      disabled={option.disabled || submitting}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '8px 14px',
        borderRadius: '8px',
        border: isSelected ? '1.5px solid var(--color-primary)' : '1px solid var(--color-border-1)',
        background: isSelected ? 'var(--color-primary-light-1, rgba(22,119,255,0.06))' : 'var(--color-bg-1)',
        cursor: option.disabled ? 'not-allowed' : 'pointer',
        opacity: option.disabled ? 0.5 : 1,
        fontSize: '13px',
        color: 'var(--color-text-1)',
        transition: 'all 0.15s ease',
        textAlign: 'left',
        width: '100%',
      }}
      onMouseEnter={e => {
        if (!option.disabled) {
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-primary)';
          (e.currentTarget as HTMLElement).style.background = 'var(--color-primary-light-1, rgba(22,119,255,0.04))';
        }
      }}
      onMouseLeave={e => {
        if (!isSelected) {
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border-1)';
          (e.currentTarget as HTMLElement).style.background = 'var(--color-bg-1)';
        }
      }}
    >
      {request.multiple && (
        <span style={{
          width: '16px',
          height: '16px',
          borderRadius: '4px',
          border: isSelected ? '1.5px solid var(--color-primary)' : '1.5px solid var(--color-border-2)',
          background: isSelected ? 'var(--color-primary)' : 'transparent',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          transition: 'all 0.15s ease',
        }}>
          {isSelected && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
              <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
          {option.icon && <span>{option.icon}</span>}
          <span>{option.label}</span>
          {option.recommended && (
            <span style={{
              fontSize: '11px',
              padding: '1px 6px',
              borderRadius: '4px',
              background: 'rgba(22,119,255,0.1)',
              color: 'var(--color-primary)',
              fontWeight: 500,
            }}>推荐</span>
          )}
        </div>
        {option.description && (
          <div style={{ fontSize: '12px', color: 'var(--color-text-3)', marginTop: '2px' }}>
            {option.description}
          </div>
        )}
      </div>
    </button>
  );

  const renderButtons = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {request.options.map(option =>
        renderOptionCard(option, false, () => handleButtonClick(option.key))
      )}
    </div>
  );

  const renderCheckboxes = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {request.options.map(option =>
        renderOptionCard(
          option,
          selectedKeys.includes(option.key),
          () => handleCheckboxChange(option.key)
        )
      )}
      <button
        type="button"
        disabled={selectedKeys.length < request.min_select || submitting}
        onClick={handleConfirm}
        style={{
          marginTop: '4px',
          padding: '7px 20px',
          borderRadius: '6px',
          border: 'none',
          background: selectedKeys.length >= request.min_select ? 'var(--color-primary)' : 'var(--color-fill-3)',
          color: selectedKeys.length >= request.min_select ? '#fff' : 'var(--color-text-3)',
          fontSize: '13px',
          fontWeight: 500,
          cursor: selectedKeys.length >= request.min_select ? 'pointer' : 'not-allowed',
          alignSelf: 'flex-start',
          transition: 'all 0.15s ease',
        }}
      >
        {t('chat.choiceConfirm')}
      </button>
    </div>
  );

  const renderTextInput = () => (
    <div style={{ display: 'flex', gap: '8px' }}>
      <Input
        value={textInput}
        onChange={e => setTextInput(e.target.value)}
        onPressEnter={handleTextSubmit}
        placeholder={t('chat.choiceTextPlaceholder') || '输入你的回答...'}
        disabled={submitting}
        style={{ flex: 1, borderRadius: '8px' }}
      />
      <button
        type="button"
        disabled={!textInput.trim() || submitting}
        onClick={handleTextSubmit}
        style={{
          padding: '4px 16px',
          borderRadius: '8px',
          border: 'none',
          background: textInput.trim() ? 'var(--color-primary)' : 'var(--color-fill-3)',
          color: textInput.trim() ? '#fff' : 'var(--color-text-3)',
          fontSize: '13px',
          fontWeight: 500,
          cursor: textInput.trim() ? 'pointer' : 'not-allowed',
          transition: 'all 0.15s ease',
        }}
      >
        {t('chat.choiceConfirm') || '确认'}
      </button>
    </div>
  );

  const renderDropdown = () => (
    <Select
      size="middle"
      placeholder={t('chat.choicePlaceholder')}
      style={{ width: '100%' }}
      disabled={submitting}
      loading={submitting}
      onChange={handleDropdownChange}
      options={request.options.map(option => ({
        value: option.key,
        label: option.label,
        disabled: option.disabled,
        title: option.description,
      }))}
    />
  );

  return (
    <div
      data-a2ui-component={a2uiComponent}
      data-a2ui-version={a2uiVersion}
      data-a2ui-event={request.a2ui?.event_name || 'user_choice_request'}
      style={{
        margin: '8px 0',
        padding: '14px 16px',
        borderRadius: '12px',
        border: '1px solid var(--color-border-1)',
        background: 'var(--color-bg-1)',
        maxWidth: '380px',
      }}
    >
      {/* Title */}
      <div style={{
        fontSize: '13px',
        fontWeight: 600,
        color: 'var(--color-text-1)',
        marginBottom: '10px',
      }}>
        {request.title}
      </div>

      {/* Description */}
      {request.description && (
        <div style={{ fontSize: '12px', color: 'var(--color-text-3)', marginBottom: '10px' }}>
          {request.description}
        </div>
      )}

      {/* Options */}
      {isPending && (
        <>
          {displayMode === 'buttons' && renderButtons()}
          {displayMode === 'dropdown' && renderDropdown()}
          {displayMode === 'checkbox' && renderCheckboxes()}
          {/* Always show text input: user can click an option OR type freely */}
          {displayMode !== 'checkbox' && (
            <div style={{ marginTop: request.options.length > 0 && displayMode !== 'text' ? '10px' : '0' }}>
              {request.options.length > 0 && displayMode !== 'text' && (
                <div style={{ fontSize: '11px', color: 'var(--color-text-4)', marginBottom: '6px' }}>
                  {t('chat.choiceOrType') || '或者自行输入'}
                </div>
              )}
              {renderTextInput()}
            </div>
          )}
        </>
      )}

      {/* Timer */}
      {isPending && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          marginTop: '10px',
          fontSize: '11px',
          color: remainingSeconds <= 10 ? '#ff4d4f' : 'var(--color-text-4)',
        }}>
          <ClockCircleOutlined style={{ fontSize: '11px' }} />
          <span>{remainingSeconds}s</span>
        </div>
      )}
    </div>
  );
};

export default UserChoiceCard;
