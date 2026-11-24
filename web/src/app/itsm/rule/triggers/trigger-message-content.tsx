'use client';

import { Mentions } from 'antd';
import { useId, useRef } from 'react';
import { useTranslation } from '@/utils/i18n';

const VARIABLE_POPUP_CLASS = 'itsm-trigger-notice-variables';
const MESSAGE_VARIABLES = {
  ticket_title: 'TicketTitle',
  sn: 'Sn',
  workflow: 'Workflow',
  node: 'Node',
  ticket_link: 'TicketLink',
  creator: 'Creator',
  trigger_name: 'TriggerName',
};

interface TriggerMessageContentProps {
  ariaLabel: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function TriggerMessageContent({ ariaLabel, value, onChange, disabled }: TriggerMessageContentProps) {
  const { t } = useTranslation();
  const hintId = useId();
  const editor = useRef<HTMLDivElement>(null);
  const popupContainer = () => editor.current?.closest<HTMLElement>('[role="dialog"]') ?? document.body;
  const variables = Object.entries(MESSAGE_VARIABLES).map(([key, name]) => ({
    key, name: t(`itsm.rule.triggerNotifyVariable${name}`),
  }));
  const namesByKey = new Map(variables.map(variable => [variable.key, variable.name]));

  return <div ref={editor} className="space-y-1">
    <Mentions
      className="w-full"
      aria-label={ariaLabel}
      aria-describedby={hintId}
      getPopupContainer={popupContainer}
      popupClassName={VARIABLE_POPUP_CLASS}
      onKeyDown={event => {
        if (event.key === 'Escape' && popupContainer().querySelector(`.${VARIABLE_POPUP_CLASS}:not(.ant-mentions-dropdown-hidden)`)) {
          event.stopPropagation();
        }
      }}
      disabled={disabled}
      rows={3}
      prefix="$"
      maxLength={2000}
      value={value}
      onChange={onChange}
      validateSearch={query => /^[\p{L}\p{N}_]*$/u.test(query)}
      filterOption={(query, { value: key = '' }) =>
        [key, namesByKey.get(key) ?? ''].some(text => text.toLowerCase().includes(query.toLowerCase()))}
      notFoundContent={t('itsm.rule.triggerNotifyNoVariables')}
      options={variables.map(({ key, name }) => ({
        value: key,
        label: <span className="flex flex-wrap items-baseline gap-x-2">
          <span>{name}</span>
          <span className="font-mono text-xs text-[var(--color-text-3)]">{'$' + key}</span>
        </span>,
      }))}
    />
    <p id={hintId} className="m-0 text-xs text-[var(--color-text-3)]">{t('itsm.rule.triggerNotifyVariableHint')}</p>
  </div>;
}
