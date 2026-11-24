'use client';

import { CloseOutlined, DownOutlined } from '@ant-design/icons';
import { Button, ConfigProvider, Input, Popover, Radio, Segmented, Select } from 'antd';
import { useId, useRef, useState, type ReactNode } from 'react';
import { UserSelector } from '@/app/itsm/components/user-selector';
import { useTranslation } from '@/utils/i18n';
import {
  newTriggerNotice, scopedFormFieldGroups, TRIGGER_NOTICE_ROLES,
  type ActionRow, type NoticeChannel, type TriggerDraft, type TriggerNotice, type TriggerNoticeOptions,
} from './trigger-config';
import { TriggerMessageContent } from './trigger-message-content';

interface NamedOption<Value extends string | number> {
  value: Value;
  label: string;
}

function optionsWithSelection<Value extends string | number>(
  options: NamedOption<Value>[], selected: Value[], missing: (value: Value) => string,
) {
  return [...options, ...selected.filter(value => !options.some(option => option.value === value))
    .map(value => ({ value, label: missing(value) }))];
}

function channelKey(channel: NoticeChannel): string | number {
  return channel.type === 'site' ? 'site' : channel.channel_id;
}

function NotifyField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 space-y-1">
    <span className="block text-xs text-[var(--color-text-2)]">{label}</span>
    {children}
  </div>;
}

interface TriggerNotificationProps {
  action: ActionRow;
  position: number;
  catalog?: TriggerNoticeOptions;
  scope: TriggerDraft['scope'];
  readOnly: boolean;
  update: (changes: Partial<ActionRow>) => void;
}

const recipientSources = [
  { key: 'roles', label: 'Roles' },
  { key: 'users', label: 'Users' },
  { key: 'group_ids', label: 'Groups' },
  { key: 'field_keys', label: 'PersonFields' },
] as const;
type RecipientSource = typeof recipientSources[number]['key'];
type Recipients = TriggerNotice['recipients'];

interface RecipientPickerProps {
  recipients: Recipients;
  position: number;
  catalog?: TriggerNoticeOptions;
  scope: TriggerDraft['scope'];
  readOnly: boolean;
  onChange: (recipients: Recipients) => void;
}

function RecipientPicker({ recipients, position, catalog, scope, readOnly, onChange }: RecipientPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [activeSource, setActiveSource] = useState<RecipientSource>('roles');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupId = useId();
  const label = (key: string) => t(`itsm.rule.triggerNotify${key}`);
  const inputLabel = (key: string) => `${label(key)} ${position}`;
  const missing = (value: string | number) => t('itsm.rule.triggerNotifyUnavailable', undefined, { value });
  const fieldOptions = new Map<string, { names: Set<string>; captions: Set<string> }>();
  for (const group of scopedFormFieldGroups(catalog?.form_field_groups ?? [], scope)) {
    for (const field of group.fields) {
      const option = fieldOptions.get(field.key) ?? { names: new Set<string>(), captions: new Set<string>() };
      option.names.add(field.label);
      option.captions.add(`${field.label} · ${group.name}`);
      fieldOptions.set(field.key, option);
    }
  }
  const hasMultipleFieldNames = recipients.field_keys.some(key => (fieldOptions.get(key)?.names.size ?? 0) > 1);

  const groupOptions = optionsWithSelection<number>((catalog?.groups ?? []).map(group => ({ value: group.id, label: group.name })), recipients.group_ids, missing);
  const personOptions = optionsWithSelection<string>(
    [...fieldOptions].map(([value, option]) => ({ value, label: [...option.captions].join(' / ') })), recipients.field_keys, missing,
  );
  const roleOptions = TRIGGER_NOTICE_ROLES.map(value => ({ value, label: label(value === 'creator' ? 'Creator' : 'CurrentAssignees') }));
  const selectedBySource = {
    roles: roleOptions.filter(option => recipients.roles.includes(option.value)).map(({ value, label }) => ({ value, name: label })),
    users: recipients.users.map(value => ({ value, name: value })),
    group_ids: groupOptions.filter(option => recipients.group_ids.includes(option.value)).map(({ value, label }) => ({ value, name: label })),
    field_keys: recipients.field_keys.map(value => ({ value, name: [...(fieldOptions.get(value)?.names ?? [])].join(' / ') || missing(value) })),
  };
  const chips = recipientSources.flatMap(source => selectedBySource[source.key].map(chip => ({ ...source, ...chip })));
  const controlsDisabled = readOnly || !catalog;
  const controls = {
    roles: <Select className="w-full" mode="multiple" aria-label={inputLabel('Roles')} allowClear
      value={recipients.roles} placeholder={label('RolesPlaceholder')} options={roleOptions}
      onChange={roles => onChange({ ...recipients, roles })} />,
    users: <UserSelector ariaLabel={inputLabel('Users')} value={recipients.users} allowClear
      onChange={users => onChange({ ...recipients, users })} />,
    group_ids: <Select className="w-full" mode="multiple" aria-label={inputLabel('Groups')} allowClear
      showSearch optionFilterProp="label" placeholder={label('GroupsPlaceholder')} disabled={controlsDisabled}
      options={groupOptions} value={recipients.group_ids} onChange={group_ids => onChange({ ...recipients, group_ids })} />,
    field_keys: <Select className="w-full" mode="multiple" aria-label={inputLabel('PersonFields')} allowClear
      showSearch filterOption={(input, option) => !!option && `${option.label} ${option.value}`.toLowerCase().includes(input.trim().toLowerCase())}
      optionRender={({ data }) => <span className="block break-words whitespace-normal" title={data.label}>{data.label}</span>}
      placeholder={label('PersonFieldsPlaceholder')} disabled={controlsDisabled}
      notFoundContent={label('NoPersonFields')} options={personOptions} value={recipients.field_keys}
      onChange={field_keys => onChange({ ...recipients, field_keys })} />,
  };
  const popupVisible = open && !readOnly;
  const popup = <div id={popupId} role="dialog" aria-label={inputLabel('Recipients')}
    className="w-[min(28rem,calc(100vw-48px))] space-y-3"
    ref={node => {
      if (node && document.activeElement === triggerRef.current) node.querySelector<HTMLInputElement>('input:checked')?.focus();
    }}
    onKeyDown={event => {
      if (event.key !== 'Escape') return;
      const target = event.target;
      event.stopPropagation();
      if (target instanceof HTMLElement && target.getAttribute('aria-expanded') === 'true') return;
      setOpen(false);
      triggerRef.current?.focus();
    }}>
    <Segmented<RecipientSource> block options={recipientSources.map(source => ({
      value: source.key,
      label: <span className="inline-block whitespace-normal text-xs">{label(source.label)}</span>,
    }))} value={activeSource} onChange={setActiveSource} />
    <div>
      <ConfigProvider getPopupContainer={trigger => trigger.parentElement ?? document.body}>
        {controls[activeSource]}
      </ConfigProvider>
    </div>
    <p className="m-0 text-xs text-[var(--color-text-3)]">{label('RecipientsHint')}</p>
  </div>;

  return <NotifyField label={label('Recipients')}>
    <Popover placement="bottomLeft" arrow={false} trigger="click" open={popupVisible} onOpenChange={setOpen} content={popup} destroyOnHidden
      getPopupContainer={trigger => trigger.closest<HTMLElement>('[role="dialog"]') ?? document.body}>
      <div className={`flex min-h-8 min-w-0 items-center gap-1.5 rounded-md border border-[var(--color-border)] px-2 py-1 ${readOnly ? '' : 'cursor-pointer hover:border-[var(--color-primary)]'}`}>
        {chips.length > 0 && <ul aria-label={inputLabel('SelectedRecipients')} className="m-0 flex min-w-0 flex-wrap items-center gap-1 p-0">
          {chips.map(chip => <li key={`${chip.key}:${chip.value}`} title={chip.name}
            className="inline-flex min-w-0 max-w-full items-center gap-1 rounded bg-[var(--color-fill-2)] px-1.5 py-0.5 text-xs">
            <span className="shrink-0 text-[var(--color-text-3)]">{label(chip.label)}</span>
            <span className="truncate">{chip.name}</span>
            {!readOnly && <button type="button" className="inline-flex shrink-0 items-center p-0.5 text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
              aria-label={t('itsm.rule.triggerNotifyRemoveRecipient', undefined, { value: chip.name })}
              onClick={event => {
                event.stopPropagation();
                const remaining = recipients[chip.key].filter(value => value !== chip.value);
                onChange({ ...recipients, [chip.key]: remaining });
              }}>
              <CloseOutlined aria-hidden className="text-[10px]" />
            </button>}
          </li>)}
        </ul>}
        {!readOnly && <button ref={triggerRef} type="button" className="flex min-w-6 flex-1 items-center justify-between gap-1 self-stretch px-1 text-left text-sm text-[var(--color-text-3)]"
          aria-label={inputLabel('Recipients')} aria-haspopup="dialog" aria-expanded={popupVisible} aria-controls={popupVisible ? popupId : undefined}
          onKeyDown={event => {
            if (event.key === 'Escape' && popupVisible) {
              event.stopPropagation();
              setOpen(false);
            }
          }}>
          {chips.length === 0 && <span>{label('RecipientsPlaceholder')}</span>}
          <DownOutlined aria-hidden className={`ml-auto text-xs ${popupVisible ? 'rotate-180' : ''}`} />
        </button>}
      </div>
    </Popover>
    {recipients.roles.includes('current_assignees') && <p className="m-0 text-xs text-[var(--color-text-3)]">{label('CurrentAssigneesHint')}</p>}
    {hasMultipleFieldNames && <p className="m-0 text-xs text-[var(--color-text-3)]">{label('SharedFieldHint')}</p>}
  </NotifyField>;
}

export function TriggerNotification({ action, position, catalog, scope, readOnly, update }: TriggerNotificationProps) {
  const { t } = useTranslation();
  const notice = action.notice;
  const contentLabel = t('itsm.rule.triggerNoticeContent');
  const content = <NotifyField label={contentLabel}>
    <Input.TextArea maxLength={2000} aria-label={`${contentLabel} ${position}`} autoSize={{ minRows: 2, maxRows: 5 }}
      value={action.value} onChange={event => update({ value: event.target.value })} />
  </NotifyField>;
  if (!notice) {
    return <div className="col-span-full space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-xs text-[var(--color-text-3)]">{t('itsm.rule.triggerNotifyLegacyHint')}</p>
        {!readOnly && <Button size="small" onClick={() => update({
          notice: { ...newTriggerNotice(), content_mode: action.value.trim() ? undefined : 'template' },
        })}>
          {t('itsm.rule.triggerNotifyConfigure')}
        </Button>}
      </div>
      {content}
    </div>;
  }

  const label = (key: string) => t(`itsm.rule.triggerNotify${key}`);
  const inputLabel = (key: string) => `${label(key)} ${position}`;
  const missing = (value: string | number) => t('itsm.rule.triggerNotifyUnavailable', undefined, { value });
  const { recipients, channels } = notice;
  const channelOptions = optionsWithSelection(
    [{ value: 'site', label: label('Site') }, ...(catalog?.channels ?? []).map(channel => ({ value: channel.id, label: channel.name }))],
    channels.map(channelKey), missing,
  );
  const controlsDisabled = readOnly || !catalog;

  return <div className="col-span-full space-y-3 rounded-md border border-[var(--color-border)] p-3">
    <RecipientPicker recipients={recipients} position={position} catalog={catalog} scope={scope} readOnly={readOnly}
      onChange={next => update({ notice: { ...notice, recipients: next } })} />
    <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
      <NotifyField label={label('Channels')}>
        <Select className="w-full" mode="multiple" aria-label={inputLabel('Channels')} allowClear
          showSearch optionFilterProp="label" placeholder={label('ChannelsPlaceholder')} disabled={controlsDisabled}
          options={channelOptions} value={channels.map(channelKey)} onChange={values => {
            const next: NoticeChannel[] = values.map((value: string | number) => channels.find(channel => channelKey(channel) === value)
              ?? (typeof value === 'number' ? { type: 'im', channel_id: value } : { type: 'site' }));
            update({ notice: { ...notice, channels: next } });
          }} />
      </NotifyField>
      <NotifyField label={label('ContentSource')}>
        <Radio.Group aria-label={inputLabel('ContentSource')} value={notice.content_mode ?? 'template'} disabled={readOnly}
          options={[
            { value: 'template', label: label('UseTemplate') },
            { value: 'custom', label: label('CustomMessage') },
          ]}
          onChange={event => update({ notice: { ...notice, content_mode: event.target.value } })} />
      </NotifyField>
      {notice.content_mode !== 'custom' && channels.map(channel => {
        const key = channelKey(channel);
        const name = channelOptions.find(option => option.value === key)?.label;
        const templateOptions = (catalog?.templates ?? []).filter(template => template.channel_type === channel.type).map(template => ({
          value: template.id, label: t('itsm.rule.triggerNotifyTemplateName', undefined, { title: template.title_tpl, event: template.event }),
        }));
        return <NotifyField label={`${label('Template')} · ${name}`} key={key}>
          <Select className="w-full" aria-label={`${inputLabel('Template')} · ${name}`} showSearch allowClear optionFilterProp="label"
            placeholder={label('DefaultTemplate')} disabled={controlsDisabled}
            options={optionsWithSelection(templateOptions, channel.template_id ? [channel.template_id] : [], missing)}
            value={channel.template_id} onChange={template_id => update({
              notice: { ...notice, channels: channels.map(item => channelKey(item) === key ? { ...item, template_id } : item) },
            })} />
        </NotifyField>;
      })}
    </div>
    {notice.content_mode === 'custom' && <NotifyField label={contentLabel}>
      <TriggerMessageContent ariaLabel={`${contentLabel} ${position}`} disabled={readOnly} value={action.value}
        onChange={value => update({ value })} />
    </NotifyField>}
  </div>;
}
