'use client';

import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, ConfigProvider, Input, Radio, Select } from 'antd';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ItsmDrawer } from '@/app/itsm/components/interaction-surfaces';
import { useTranslation } from '@/utils/i18n';
import { ConditionFields } from './condition-fields';
import { conditionFieldCatalog, type ConditionFieldCatalog } from './trigger-condition-fields';
import { TriggerNotification } from './trigger-notification';
import {
  buildTriggerPayload, newCondition, newConditionGroup, newTriggerAction, newTriggerNotice, readTriggerDraft,
  TRIGGER_ACTIONS, TRIGGER_EVENTS, TRIGGER_SCOPES,
  type ConditionGroupDraft, type ScopeMode, type TriggerDraft, type TriggerItem, type TriggerOptions,
} from './trigger-config';

type Payload = ReturnType<typeof buildTriggerPayload>;
interface SectionProps { title: string; hint?: string; children: ReactNode }
const parameterLabels = { tag: 'triggerTagName', status: 'triggerTargetStatus' } as const;

function Section({ title, hint, children }: SectionProps) {
  return <section className="space-y-3 border-t border-[var(--color-border)] pt-4">
    <div>
      <h3 className="m-0 text-sm font-semibold">{title}</h3>
      {hint && <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">{hint}</p>}
    </div>
    {children}
  </section>;
}

interface GroupProps {
  group: ConditionGroupDraft;
  change: (group: ConditionGroupDraft) => void;
  catalog: ConditionFieldCatalog;
  depth?: number;
  position?: string;
}

function ConditionGroup({ group, change, catalog, depth = 0, position = '' }: GroupProps) {
  const { t } = useTranslation();
  return <div className={depth ? 'min-w-0 space-y-3 border-l border-[var(--color-border)] pl-3' : 'min-w-0 space-y-3'}>
    <div className="flex flex-wrap items-center gap-2">
      {group.items.length > 0 && <Radio.Group aria-label={t('itsm.rule.triggerMatchMode')} value={group.logic}
        options={[{ value: 'and', label: t('itsm.rule.triggerMatchAll') }, { value: 'or', label: t('itsm.rule.triggerMatchAny') }]}
        onChange={event => change({ ...group, logic: event.target.value })} />}
      <Button icon={<PlusOutlined />} aria-label={t('itsm.rule.triggerAddCondition')} onClick={() => change({ ...group, items: [...group.items, newCondition()] })}>
        {t('itsm.rule.triggerAddCondition')}
      </Button>
      {depth < 2 && <Button type="text" icon={<PlusOutlined />} aria-label={t('itsm.rule.triggerAddConditionGroup')}
        onClick={() => change({ ...group, items: [...group.items, newConditionGroup([newCondition()])] })}>
        {t('itsm.rule.triggerAddConditionGroup')}
      </Button>}
    </div>
    <ul className="m-0 list-none space-y-3 p-0">
      {group.items.map((row, index) => {
        const rowPosition = position ? `${position}.${index + 1}` : String(index + 1);
        const update = (next: ConditionGroupDraft['items'][number]) => change({
          ...group, items: group.items.map(item => item.id === row.id ? next : item),
        });
        return <li className="flex items-start gap-2" key={row.id}>
          {row.kind === 'group'
            ? <div className="min-w-0 flex-1"><ConditionGroup group={row} change={update} catalog={catalog} depth={depth + 1} position={rowPosition} /></div>
            : <ConditionFields row={row} change={update} position={rowPosition} catalog={catalog} />}
          <Button type="text" icon={<DeleteOutlined />} aria-label={t('itsm.rule.triggerRemoveCondition', undefined, { position: rowPosition })}
            onClick={() => change({ ...group, items: group.items.filter(item => item.id !== row.id) })} />
        </li>;
      })}
    </ul>
  </div>;
}

interface TriggerEditorProps {
  item?: TriggerItem;
  getOptions: () => Promise<TriggerOptions>;
  onCancel: () => void;
  onSave?: (payload: Payload) => Promise<void>;
}

export function TriggerEditor({ item, getOptions, onCancel, onSave }: TriggerEditorProps) {
  const { t } = useTranslation();
  const readOnly = !onSave;
  const [draft, setDraft] = useState(() => readTriggerDraft(item));
  const [choices, setChoices] = useState<TriggerOptions | null>(null);
  const [choicesError, setChoicesError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const optionsRequest = useRef<{ attempt: number; load: typeof getOptions; promise: Promise<TriggerOptions> } | null>(null);

  useEffect(() => {
    let active = true;
    const cached = optionsRequest.current;
    if (!cached || cached.attempt !== attempt || cached.load !== getOptions) {
      optionsRequest.current = { attempt, load: getOptions, promise: getOptions() };
    }
    void optionsRequest.current?.promise.then(result => { if (active) setChoices(result); })
      .catch(() => { if (active) setChoicesError(true); });
    return () => { active = false; };
  }, [getOptions, attempt]);

  const catalog = useMemo(() => conditionFieldCatalog(choices, draft.scope), [choices, draft.scope]);
  const patch = (changes: Partial<TriggerDraft>) => setDraft(current => ({ ...current, ...changes }));

  const save = async () => {
    const payload = (() => {
      try {
        return buildTriggerPayload(draft);
      } catch (error) {
        throw new Error(t(error instanceof Error ? error.message : 'itsm.rule.triggerValidationFailed'));
      }
    })();
    if (payload.config.actions.some(action => action.type === 'status' && !choices?.statuses.some(status => status.key === action.value))) {
      throw new Error(t('itsm.rule.triggerStatusRequired'));
    }
    await onSave?.(payload);
  };

  const title = item ? (readOnly ? t('itsm.rule.viewTrigger') : t('itsm.rule.editTrigger')) : t('itsm.rule.newTrigger');
  const form = (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="min-w-0 space-y-1">
          <span className="text-sm font-medium">{t('itsm.portal.name')}</span>
          <Input aria-label={t('itsm.portal.name')} value={draft.name} maxLength={128}
            onChange={event => patch({ name: event.target.value })} />
        </div>
        <div className="min-w-0 space-y-1">
          <span className="text-sm font-medium">{t('itsm.rule.event')}</span>
          <Select className="w-full" aria-label={t('itsm.rule.event')} value={draft.event}
            options={TRIGGER_EVENTS.map(value => ({ value, label: t(`itsm.rule.${value}`) }))}
            onChange={event => patch({ event })} />
          {draft.event === 'ticket_end' && <p className="m-0 text-xs text-[var(--color-text-3)]">{t('itsm.rule.triggerEndHint')}</p>}
        </div>
      </div>
      {choicesError && <Alert type="error" showIcon message={t('itsm.rule.triggerOptionsFailed')}
        action={<Button size="small" disabled={false} onClick={() => { setChoicesError(false); setAttempt(current => current + 1); }}>
          {t('common.retry')}
        </Button>} />}
      <Section title={t('itsm.rule.triggerScope')} hint={draft.scope.mode === 'all' ? undefined : t('itsm.rule.triggerScopeHint')}>
        <Radio.Group aria-label={t('itsm.rule.triggerScope')} value={draft.scope.mode}
          options={(['all', 'include', 'exclude'] satisfies ScopeMode[]).map(value => ({
            value, label: t(`itsm.rule.triggerScope_${value}`),
          }))}
          onChange={event => patch({ scope: { ...draft.scope, mode: event.target.value } })} />
        {draft.scope.mode !== 'all' && <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {TRIGGER_SCOPES.map(({ key, options, labelKey }) => <div className="min-w-0 space-y-1" key={key}>
            <span className="text-xs text-[var(--color-text-2)]">{t(`itsm.rule.${labelKey}`)}</span>
            <Select mode="multiple" maxTagCount="responsive" className="w-full" aria-label={t(`itsm.rule.${labelKey}`)}
              showSearch optionFilterProp="label" placeholder={t('itsm.rule.triggerScopePlaceholder')}
              value={draft.scope[key] ?? []} loading={!choices && !choicesError} disabled={readOnly || !choices}
              options={choices?.[options].map(choice => ({ value: choice.id, label: choice.name }))}
              onChange={ids => patch({ scope: { ...draft.scope, [key]: ids } })} />
          </div>)}
        </div>}
      </Section>
      <Section title={t('itsm.rule.when')} hint={t(draft.when.items.length ? 'itsm.rule.triggerFieldCatalogHint' : 'itsm.rule.triggerConditionHint')}>
        {draft.when.items.length > 0 && draft.scope.mode === 'include' && !catalog.formFields.length && choices && <p
          className="m-0 text-xs text-[var(--color-text-3)]">{t(TRIGGER_SCOPES.some(({ key }) => draft.scope[key]?.length)
            ? 'itsm.rule.triggerNoScopedFields' : 'itsm.rule.triggerFieldScopeHint')}</p>}
        <ConditionGroup group={draft.when} change={when => patch({ when })} catalog={catalog} />
      </Section>
      <Section title={t('itsm.rule.response')} hint={t('itsm.rule.triggerActionHint')}>
        <ol className="m-0 list-none divide-y divide-[var(--color-border)] p-0">
          {draft.actions.map((action, index) => {
            const position = index + 1;
            const parameterLabel = parameterLabels[action.type as keyof typeof parameterLabels];
            const parameter = t(parameterLabel ? `itsm.rule.${parameterLabel}` : 'itsm.rule.value');
            const update = (patch: Partial<typeof action>) => setDraft(current => ({
              ...current, actions: current.actions.map(row => row.id === action.id ? { ...row, ...patch } : row),
            }));
            const move = (offset: number) => setDraft(current => {
              const actions = [...current.actions];
              const from = actions.findIndex(row => row.id === action.id);
              const to = from + offset;
              if (to < 0 || to >= actions.length) return current;
              [actions[from], actions[to]] = [actions[to], actions[from]];
              return { ...current, actions };
            });
            return <li key={action.id} className="grid grid-cols-1 items-start gap-2 py-3 first:pt-0 sm:grid-cols-[8rem_minmax(0,1fr)_auto]">
              <div className={action.type === 'notice' ? 'min-w-0 max-w-52 space-y-1 sm:col-span-2' : 'min-w-0 space-y-1'}>
                <span className="text-xs text-[var(--color-text-2)]">{t('itsm.rule.triggerAction')} {position}</span>
                <Select className="w-full" aria-label={`${t('itsm.rule.triggerAction')} ${position}`} value={action.type}
                  options={TRIGGER_ACTIONS.map(option => ({ value: option.value, label: t(`itsm.rule.${option.labelKey}`) }))}
                  onChange={type => update({ type, value: '', notice: type === 'notice' ? newTriggerNotice() : undefined })} />
              </div>
              {action.type !== 'notice' && <div className="min-w-0 space-y-1">
                <span className="text-xs text-[var(--color-text-2)]">{parameter}</span>
                {action.type === 'status'
                  ? <Select className="w-full" aria-label={`${parameter} ${position}`} value={action.value || undefined}
                    showSearch optionFilterProp="label" loading={!choices && !choicesError} disabled={readOnly || !choices}
                    options={choices?.statuses.map(status => ({ label: status.name, value: status.key }))}
                    onChange={value => update({ value })} />
                  : <Input aria-label={`${parameter} ${position}`} maxLength={64}
                    value={action.value} onChange={event => update({ value: event.target.value })} />}
              </div>}
              <div className="flex gap-1 sm:mt-5">
                <Button type="text" icon={<ArrowUpOutlined />} disabled={readOnly || index === 0}
                  aria-label={t('itsm.rule.triggerMoveUp', undefined, { position })} onClick={() => move(-1)} />
                <Button type="text" icon={<ArrowDownOutlined />} disabled={readOnly || position === draft.actions.length}
                  aria-label={t('itsm.rule.triggerMoveDown', undefined, { position })} onClick={() => move(1)} />
                <Button type="text" icon={<DeleteOutlined />} disabled={readOnly || draft.actions.length === 1}
                  aria-label={t('itsm.rule.triggerRemoveAction', undefined, { position })}
                  onClick={() => patch({ actions: draft.actions.filter(row => row.id !== action.id) })} />
              </div>
              {action.type === 'notice' && <TriggerNotification action={action} position={position}
                catalog={choices?.notice} scope={draft.scope} readOnly={readOnly} update={update} />}
            </li>;
          })}
        </ol>
        <Button icon={<PlusOutlined />} aria-label={t('itsm.rule.triggerAddAction')} onClick={() => patch({ actions: [...draft.actions, newTriggerAction()] })}>
          {t('itsm.rule.triggerAddAction')}
        </Button>
      </Section>
    </div>
  );

  return <ItsmDrawer open destroyOnHidden width="min(860px, 100vw)" title={title}
    formValue={draft} onCancel={onCancel} onOk={readOnly ? undefined : save}>
    <ConfigProvider componentDisabled={readOnly || undefined}>{form}</ConfigProvider>
  </ItsmDrawer>;
}
