'use client';

import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {Button, Checkbox, message as antMessage, Select} from 'antd';
import {CheckCircleOutlined, ClockCircleOutlined, ExclamationCircleOutlined, StarFilled} from '@ant-design/icons';
import {useTranslation} from '@/utils/i18n';
import {UserChoiceOption, UserChoiceRequest} from '@/app/opspilot/types/global';

interface UserChoiceCardProps {
  request: UserChoiceRequest;
  token: string;
  onSubmit: (choiceId: string, status: 'submitted' | 'timeout', selected: string[]) => void;
}

const UserChoiceCard: React.FC<UserChoiceCardProps> = ({ request, token, onSubmit }) => {
  const { t } = useTranslation();
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    const elapsed = (Date.now() - request.received_at) / 1000;
    return Math.max(0, Math.floor(request.timeout_seconds - elapsed));
  });

  // Determine display mode based on hint and options count
  const displayMode = useMemo(() => {
    if (request.multiple) return 'checkbox';
    if (request.display_hint !== 'auto') return request.display_hint;
    return request.options.length <= 5 ? 'buttons' : 'dropdown';
  }, [request.multiple, request.display_hint, request.options.length]);

  // Countdown timer
  useEffect(() => {
    if (request.status !== 'pending') return;
    const timer = setInterval(() => {
      const elapsed = (Date.now() - request.received_at) / 1000;
      const remaining = Math.max(0, Math.floor(request.timeout_seconds - elapsed));
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
      }
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
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      onSubmit(request.choice_id, 'submitted', keys);
    } catch {
      antMessage.error(t('chat.choiceSubmitFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [token, request, onSubmit, t]);

  // Single-select button click handler (immediate submit)
  const handleButtonClick = useCallback((key: string) => {
    handleSubmit([key]);
  }, [handleSubmit]);

  // Multi-select confirm handler
  const handleConfirm = useCallback(() => {
    handleSubmit(selectedKeys);
  }, [handleSubmit, selectedKeys]);

  // Checkbox change handler
  const handleCheckboxChange = useCallback((key: string, checked: boolean) => {
    setSelectedKeys(prev => {
      if (checked) {
        if (request.max_select > 0 && prev.length >= request.max_select) {
          antMessage.warning(t('chat.choiceMaxSelect', undefined, { max: request.max_select }));
          return prev;
        }
        return [...prev, key];
      }
      return prev.filter(k => k !== key);
    });
  }, [request.max_select, t]);

  // Dropdown change handler
  const handleDropdownChange = useCallback((value: string) => {
    handleSubmit([value]);
  }, [handleSubmit]);

  const isTimedOut = remainingSeconds <= 0 && request.status === 'pending';
  const isPending = request.status === 'pending' && !isTimedOut;
  const isCompleted = request.status === 'submitted' || request.status === 'timeout' || isTimedOut;

  const statusIcon = () => {
    if (request.status === 'submitted') return <CheckCircleOutlined className="text-green-500" />;
    if (request.status === 'timeout' || isTimedOut) return <ExclamationCircleOutlined className="text-orange-500" />;
    return <ClockCircleOutlined className="text-blue-500" />;
  };

  const statusText = () => {
    if (request.status === 'submitted') {
      const selectedLabels = request.selected?.map(key => 
        request.options.find(o => o.key === key)?.label || key
      ).join(', ');
      return `${t('chat.choiceSelected')}: ${selectedLabels}`;
    }
    if (request.status === 'timeout' || isTimedOut) return t('chat.choiceTimeout');
    return `${t('chat.approvalTimeRemaining')}: ${remainingSeconds}s`;
  };

  const renderOption = (option: UserChoiceOption) => (
    <span className="flex items-center gap-1">
      {option.icon && <span>{option.icon}</span>}
      <span>{option.label}</span>
      {option.recommended && <StarFilled className="text-yellow-500 text-xs" />}
    </span>
  );

  const renderButtons = () => (
    <div className="flex flex-wrap gap-2">
      {request.options.map(option => (
        <Button
          key={option.key}
          size="small"
          type={option.recommended ? 'primary' : 'default'}
          disabled={option.disabled || submitting}
          loading={submitting}
          onClick={() => handleButtonClick(option.key)}
          title={option.description}
        >
          {renderOption(option)}
        </Button>
      ))}
    </div>
  );

  const renderDropdown = () => (
    <Select
      size="small"
      placeholder={t('chat.choicePlaceholder')}
      className="w-full"
      disabled={submitting}
      loading={submitting}
      onChange={handleDropdownChange}
      options={request.options.map(option => ({
        value: option.key,
        label: renderOption(option),
        disabled: option.disabled,
        title: option.description,
      }))}
    />
  );

  const renderCheckboxes = () => {
    const isMaxReached = request.max_select > 0 && selectedKeys.length >= request.max_select;
    
    return (
      <div className="flex flex-col gap-1">
        {request.options.map(option => {
          const isChecked = selectedKeys.includes(option.key);
          // Disable unchecked options when max is reached
          const isDisabledByMax = isMaxReached && !isChecked;
          
          return (
            <Checkbox
              key={option.key}
              disabled={option.disabled || submitting || isDisabledByMax}
              checked={isChecked}
              onChange={e => handleCheckboxChange(option.key, e.target.checked)}
            >
              <span className="flex items-center gap-1" title={option.description}>
                {option.icon && <span>{option.icon}</span>}
                <span>{option.label}</span>
                {option.recommended && <StarFilled className="text-yellow-500 text-xs" />}
                {option.description && (
                  <span className="text-gray-400 text-xs ml-1">({option.description})</span>
                )}
              </span>
            </Checkbox>
          );
        })}
        <Button
          size="small"
          type="primary"
          className="mt-2 w-fit"
          disabled={selectedKeys.length < request.min_select || submitting}
          loading={submitting}
          onClick={handleConfirm}
        >
          {t('chat.choiceConfirm')}
        </Button>
      </div>
    );
  };

  // Compact view for completed state
  if (isCompleted) {
    const selectedLabels = request.selected?.map(key =>
      request.options.find(o => o.key === key)?.label || key
    ).join(', ') || '';
    const isTimeout = request.status === 'timeout' || isTimedOut;

    return (
      <div className="my-1 flex items-center gap-2 text-sm text-gray-600">
        {isTimeout ? (
          <ExclamationCircleOutlined className="text-orange-500" />
        ) : (
          <CheckCircleOutlined className="text-green-500" />
        )}
        <span>
          {isTimeout ? t('chat.choiceTimeout') : t('chat.choiceSelected')}
          {selectedLabels && `: ${selectedLabels}`}
        </span>
      </div>
    );
  }

  return (
    <div className="my-2 border border-blue-200 rounded-lg bg-blue-50 p-3 max-w-md">
      <div className="flex items-center gap-2 mb-2 font-medium text-blue-700">
        <ExclamationCircleOutlined />
        <span>{request.title}</span>
      </div>

      {request.description && (
        <div className="text-sm text-gray-600 mb-2">{request.description}</div>
      )}

      <div className="flex items-center gap-2 text-sm mb-2">
        {statusIcon()}
        <span>{statusText()}</span>
      </div>

      {isPending && (
        <>
          {displayMode === 'buttons' && renderButtons()}
          {displayMode === 'dropdown' && renderDropdown()}
          {displayMode === 'checkbox' && renderCheckboxes()}
        </>
      )}
    </div>
  );
};

export default UserChoiceCard;
