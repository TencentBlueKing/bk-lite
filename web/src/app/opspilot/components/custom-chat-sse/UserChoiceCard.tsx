'use client';

import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Input, message as antMessage, Select, Spin} from 'antd';
import {ClockCircleOutlined, LoadingOutlined} from '@ant-design/icons';
import {useTranslation} from '@/utils/i18n';
import {UserChoiceOption, UserChoiceRequest} from '@/app/opspilot/types/global';
import {postUserChoice} from './submitUserChoice';

interface UserChoiceCardProps {
  request: UserChoiceRequest;
  token: string;
  onSubmit: (choiceId: string, status: 'pending' | 'submitted' | 'timeout', selected: string[]) => void;
}

const UserChoiceCard: React.FC<UserChoiceCardProps> = ({ request, token, onSubmit }) => {
  const { t } = useTranslation();
  const a2uiComponent = request.a2ui?.component || 'user-choice';
  const a2uiVersion = request.a2ui?.version || 'legacy';
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [textInput, setTextInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
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
    // 防重复：后台慢时按钮可能仍可见一帧，或输入框路径并发提交
    if (submittingRef.current || request.status !== 'pending') return;
    submittingRef.current = true;
    setSubmitting(true);

    // 乐观关闭卡片，避免用户以为没点上而连点
    onSubmit(request.choice_id, 'submitted', keys);
    const hideLoading = antMessage.loading(t('chat.choiceSubmitting') || '正在提交选择...', 0);
    try {
      await postUserChoice(token, {
        execution_id: request.execution_id,
        node_id: request.node_id,
        choice_id: request.choice_id,
        selected: keys,
      });
    } catch {
      antMessage.error(t('chat.choiceSubmitFailed'));
      // 失败后恢复为待选，允许重试
      onSubmit(request.choice_id, 'pending', []);
    } finally {
      hideLoading();
      submittingRef.current = false;
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
      className={[
        'flex w-full items-center gap-2 rounded-lg px-3.5 py-2 text-left text-[13px] text-[var(--color-text-1)] transition-all duration-150',
        isSelected
          ? 'border-[1.5px] border-[var(--color-primary)] bg-[var(--color-primary-light-1)]'
          : 'border border-[var(--color-border-1)] bg-[var(--color-bg-1)] hover:border-[var(--color-primary)] hover:bg-[var(--color-primary-light-1)]',
        option.disabled || submitting ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
      ].join(' ')}
    >
      {request.multiple && (
        <span className={[
          'flex h-4 w-4 shrink-0 items-center justify-center rounded transition-all duration-150',
          isSelected
            ? 'border-[1.5px] border-[var(--color-primary)] bg-[var(--color-primary)]'
            : 'border-[1.5px] border-[var(--color-border-2)] bg-transparent',
        ].join(' ')}>
          {isSelected && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
              <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 font-medium">
          {option.icon && <span>{option.icon}</span>}
          <span>{option.label}</span>
          {option.recommended && (
            <span className="rounded px-1.5 py-px text-[11px] font-medium text-[var(--color-primary)] bg-[var(--color-primary-light-1)]">推荐</span>
          )}
        </div>
        {option.description && (
          <div className="mt-0.5 text-xs text-[var(--color-text-3)]">
            {option.description}
          </div>
        )}
      </div>
    </button>
  );

  const renderButtons = () => (
    <div className="flex flex-col gap-1.5">
      {request.options.map(option =>
        renderOptionCard(option, false, () => handleButtonClick(option.key))
      )}
    </div>
  );

  const renderCheckboxes = () => {
    const canConfirm = selectedKeys.length >= request.min_select;
    return (
      <div className="flex flex-col gap-1.5">
        {request.options.map(option =>
          renderOptionCard(
            option,
            selectedKeys.includes(option.key),
            () => handleCheckboxChange(option.key)
          )
        )}
        <button
          type="button"
          disabled={!canConfirm || submitting}
          onClick={handleConfirm}
          className={[
            'mt-1 self-start rounded-md px-5 py-[7px] text-[13px] font-medium transition-all duration-150',
            canConfirm
              ? 'cursor-pointer border-none bg-[var(--color-primary)] text-white'
              : 'cursor-not-allowed border-none bg-[var(--color-fill-3)] text-[var(--color-text-3)]',
          ].join(' ')}
        >
          {submitting ? (
            <span className="inline-flex items-center gap-1.5">
              <LoadingOutlined />
              {t('chat.choiceSubmitting') || '正在提交选择...'}
            </span>
          ) : (
            t('chat.choiceConfirm')
          )}
        </button>
      </div>
    );
  };

  const renderTextInput = () => {
    const canSubmit = !!textInput.trim();
    return (
      <div className="flex gap-2">
        <Input
          value={textInput}
          onChange={e => setTextInput(e.target.value)}
          onPressEnter={handleTextSubmit}
          placeholder={t('chat.choiceTextPlaceholder') || '输入你的回答...'}
          disabled={submitting}
          className="flex-1 rounded-lg"
        />
        <button
          type="button"
          disabled={!canSubmit || submitting}
          onClick={handleTextSubmit}
          className={[
            'rounded-lg px-4 py-1 text-[13px] font-medium transition-all duration-150',
            canSubmit
              ? 'cursor-pointer border-none bg-[var(--color-primary)] text-white'
              : 'cursor-not-allowed border-none bg-[var(--color-fill-3)] text-[var(--color-text-3)]',
          ].join(' ')}
        >
          {submitting ? <LoadingOutlined /> : (t('chat.choiceConfirm') || '确认')}
        </button>
      </div>
    );
  };

  const renderDropdown = () => (
    <Select
      size="middle"
      placeholder={t('chat.choicePlaceholder')}
      className="w-full"
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
      className={[
        'relative my-2 max-w-[380px] rounded-xl border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-4 py-3.5',
        submitting ? 'pointer-events-none opacity-[0.72]' : 'opacity-100',
      ].join(' ')}
    >
      {submitting && (
        <div className="absolute inset-0 z-[1] flex items-center justify-center rounded-xl bg-[rgba(255,255,255,0.55)]">
          <Spin indicator={<LoadingOutlined className="text-lg" spin />} />
        </div>
      )}

      {/* Title */}
      <div className="mb-2.5 text-[13px] font-semibold text-[var(--color-text-1)]">
        {request.title}
      </div>

      {/* Description */}
      {request.description && (
        <div className="mb-2.5 text-xs text-[var(--color-text-3)]">
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
            <div className={request.options.length > 0 && displayMode !== 'text' ? 'mt-2.5' : 'mt-0'}>
              {request.options.length > 0 && displayMode !== 'text' && (
                <div className="mb-1.5 text-[11px] text-[var(--color-text-4)]">
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
        <div className={[
          'mt-2.5 flex items-center gap-1 text-[11px]',
          remainingSeconds <= 10 ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-4)]',
        ].join(' ')}>
          <ClockCircleOutlined className="text-[11px]" />
          <span>{remainingSeconds}s</span>
        </div>
      )}
    </div>
  );
};

export default UserChoiceCard;
