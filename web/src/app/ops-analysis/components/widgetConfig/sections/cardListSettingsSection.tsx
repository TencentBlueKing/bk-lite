import React, { useEffect, useMemo, useState } from 'react';
import { DownOutlined, EyeOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { Form, Radio, Select, Tooltip } from 'antd';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import {
  buildCardListFieldOptions,
  getCardListDuplicateHintSlots,
  resolveCardListOptionalOpenState,
  resolveCardListPreviewSlots,
  type CardListFormState,
} from '../utils/cardListSettingsModel';

interface CardListSettingsSectionProps {
  t: (key: string) => string;
  availableFields: ResponseFieldDefinition[];
}

const SLOT_LABEL_KEYS: Record<string, string> = {
  title: 'dashboard.cardListTitleField',
  description: 'dashboard.cardListDescriptionField',
  leading: 'dashboard.cardListAddLeading',
  badge: 'dashboard.cardListAddBadge',
  trailing: 'dashboard.cardListAddTrailing',
};

const CardListFieldSelect = ({
  options,
  placeholder,
  hint,
  allowClear = true,
  value,
  onChange,
}: {
  options: ReturnType<typeof buildCardListFieldOptions>;
  placeholder: string;
  hint?: string;
  allowClear?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}) => (
  <>
    <Select
      allowClear={allowClear}
      showSearch
      optionFilterProp="label"
      options={options}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
    />
    {hint ? (
      <div className="mt-1 text-xs text-(--color-text-3)">{hint}</div>
    ) : null}
  </>
);

const LayoutPicker = ({
  value,
  onChange,
  listLabel,
  gridLabel,
}: {
  value?: 'list' | 'grid';
  onChange?: (value: 'list' | 'grid') => void;
  listLabel: string;
  gridLabel: string;
}) => {
  const selected = value === 'grid' ? 'grid' : 'list';
  const cardClass = (active: boolean) =>
    `flex cursor-pointer flex-col gap-2 rounded-md border-2 px-3 py-2.5 text-left transition-colors ${
      active
        ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
        : 'border-[var(--color-border-2)] bg-[var(--color-bg)] text-[var(--color-text-2)]'
    }`;
  const sketchClass = (active: boolean) =>
    `rounded-sm ${active ? 'bg-[var(--color-primary)]/35' : 'bg-[var(--color-fill-2)]'}`;

  return (
    <div className="grid grid-cols-2 gap-2" data-testid="card-list-layout-picker">
      <button
        type="button"
        aria-pressed={selected === 'list'}
        data-selected={selected === 'list' ? 'true' : 'false'}
        className={cardClass(selected === 'list')}
        onClick={() => onChange?.('list')}
      >
        <div className="space-y-1">
          <div className={`h-1.5 ${sketchClass(selected === 'list')}`} />
          <div className={`h-1.5 ${sketchClass(selected === 'list')}`} />
          <div className={`h-1.5 ${sketchClass(selected === 'list')}`} />
        </div>
        <span className="text-xs font-medium">{listLabel}</span>
      </button>
      <button
        type="button"
        aria-pressed={selected === 'grid'}
        data-selected={selected === 'grid' ? 'true' : 'false'}
        className={cardClass(selected === 'grid')}
        onClick={() => onChange?.('grid')}
      >
        <div className="grid grid-cols-2 gap-1">
          <div className={`h-4 ${sketchClass(selected === 'grid')}`} />
          <div className={`h-4 ${sketchClass(selected === 'grid')}`} />
          <div className={`h-4 ${sketchClass(selected === 'grid')}`} />
          <div className={`h-4 ${sketchClass(selected === 'grid')}`} />
        </div>
        <span className="text-xs font-medium">{gridLabel}</span>
      </button>
    </div>
  );
};

const OptionalGroup = ({
  title,
  open,
  expandLabel,
  collapseLabel,
  testId,
  tooltip,
  required,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  expandLabel: string;
  collapseLabel: string;
  testId: string;
  tooltip?: string;
  required?: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) => (
  <div>
    <button
      type="button"
      aria-expanded={open}
      data-testid={testId}
      className="flex h-auto w-full items-center justify-between px-0 py-1 text-left text-(--color-text-1)"
      onClick={onToggle}
    >
      <span className="inline-flex items-center">
        {required ? (
          <span className="mr-1 text-[var(--color-fail)]" aria-hidden>
            *
          </span>
        ) : null}
        {title}
        {tooltip ? (
          <Tooltip title={tooltip}>
            <QuestionCircleOutlined
              data-testid={`${testId}-hint`}
              className="ml-1 text-(--color-text-3) cursor-help"
              onClick={(event) => event.stopPropagation()}
            />
          </Tooltip>
        ) : null}
      </span>
      <span className="inline-flex items-center gap-1 text-xs text-(--color-text-3)">
        {open ? collapseLabel : expandLabel}
        <DownOutlined className={`text-[10px] transition-transform ${open ? 'rotate-180' : ''}`} />
      </span>
    </button>
    <div className={open ? 'pt-1' : 'hidden'} hidden={!open}>
      {children}
    </div>
  </div>
);

const LeadingTypeSegmented = ({
  value,
  onChange,
  noneLabel,
  indexLabel,
  fieldLabel,
  onClearField,
}: {
  value?: 'none' | 'index' | 'field';
  onChange?: (value: 'none' | 'index' | 'field') => void;
  noneLabel: string;
  indexLabel: string;
  fieldLabel: string;
  onClearField: () => void;
}) => (
  <Radio.Group
    optionType="button"
    value={value}
    onChange={(event) => {
      const typed = event.target.value as 'none' | 'index' | 'field';
      onChange?.(typed);
      if (typed !== 'field') {
        onClearField();
      }
    }}
  >
    <Radio.Button value="none">{noneLabel}</Radio.Button>
    <Radio.Button value="index">{indexLabel}</Radio.Button>
    <Radio.Button value="field">{fieldLabel}</Radio.Button>
  </Radio.Group>
);

const CardListPreview = ({
  label,
  slots,
}: {
  label: string;
  slots: ReturnType<typeof resolveCardListPreviewSlots>;
}) => (
  <section
    data-testid="card-list-preview"
    aria-label={label}
    className="rounded-md border border-dashed border-[var(--color-border-3)] bg-[var(--color-fill-1)] px-3 py-2.5"
  >
    <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-3)]">
      <EyeOutlined aria-hidden className="text-[12px]" />
      <span>{label}</span>
    </div>
    <article className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] px-3 py-2.5">
      <div className="flex min-w-0 items-start gap-3">
        {slots.leading ? (
          <div className="shrink-0 text-xs font-medium tabular-nums text-(--color-text-3)">
            {slots.leading}
          </div>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-(--color-text-1)">
            {slots.primary}
          </div>
          {slots.secondary ? (
            <div className="mt-0.5 line-clamp-2 text-xs text-(--color-text-2)">
              {slots.secondary}
            </div>
          ) : null}
        </div>
        {slots.badge || slots.trailingPrimary || slots.trailingSecondary ? (
          <div className="flex min-w-0 shrink-0 flex-col items-end gap-1">
            {slots.badge ? (
              <span className="inline-flex max-w-full truncate rounded-sm bg-(--color-primary-bg-active) px-1.5 py-0.5 text-xs font-medium text-(--color-text-1)">
                {slots.badge}
              </span>
            ) : null}
            {slots.trailingPrimary ? (
              <span className="max-w-full truncate text-xs font-medium text-(--color-text-1)">
                {slots.trailingPrimary}
              </span>
            ) : null}
            {slots.trailingSecondary ? (
              <span className="max-w-full truncate text-xs text-(--color-text-3)">
                {slots.trailingSecondary}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  </section>
);

export const CardListSettingsSection: React.FC<CardListSettingsSectionProps> = ({
  t,
  availableFields,
}) => {
  const form = Form.useFormInstance();
  const watchedCardList = Form.useWatch('cardList') as CardListFormState | undefined;
  const cardList = {
    ...(form.getFieldValue('cardList') || {}),
    ...watchedCardList,
  } as CardListFormState;
  const restored = resolveCardListOptionalOpenState(cardList);
  const [leadingOpen, setLeadingOpen] = useState(restored.leading);
  const [badgeOpen, setBadgeOpen] = useState(restored.badge);
  const [trailingOpen, setTrailingOpen] = useState(restored.trailing);

  useEffect(() => {
    setLeadingOpen(restored.leading);
    setBadgeOpen(restored.badge);
    setTrailingOpen(restored.trailing);
  }, [restored.leading, restored.badge, restored.trailing]);

  const fieldOptions = useMemo(
    () => buildCardListFieldOptions(availableFields),
    [availableFields],
  );
  const previewSlots = resolveCardListPreviewSlots(cardList, fieldOptions, {
    title: t('dashboard.cardListPreviewTitle'),
    description: t('dashboard.cardListPreviewDescription'),
    badge: t('dashboard.cardListPreviewBadge'),
    trailing: t('dashboard.cardListPreviewTrailing'),
    index: '01',
  });

  const duplicateHint = (fieldKey: string | undefined, currentSlot: string) => {
    const slots = getCardListDuplicateHintSlots(fieldKey, cardList, currentSlot);
    if (!slots.length) {
      return undefined;
    }
    return t('dashboard.cardListFieldUsedIn').replace(
      '{{slot}}',
      slots.map((slot) => t(SLOT_LABEL_KEYS[slot] || slot)).join(' / '),
    );
  };

  return (
    <div className="mb-6">
      <div className="mb-4 font-medium">{t('dashboard.cardListSettings')}</div>
      {availableFields.length === 0 ? (
        <div className="mb-4 text-center text-sm text-(--color-text-3)">
          {t('topology.nodeConfig.noAvailableFields')}
        </div>
      ) : null}

      <CardListPreview
        label={t('dashboard.cardListPreview')}
        slots={previewSlots}
      />

      <div className="mt-5 mb-2 font-medium">{t('dashboard.cardListContent')}</div>
      <Form.Item
        label={t('dashboard.cardListTitleField')}
        name={['cardList', 'titleField']}
        rules={[{ required: true, message: t('dashboard.cardListTitleRequired') }]}
      >
        <CardListFieldSelect
          options={fieldOptions}
          placeholder={t('dashboard.cardListSelectField')}
        />
      </Form.Item>
      <Form.Item
        label={t('dashboard.cardListDescriptionField')}
        name={['cardList', 'descriptionField']}
      >
        <CardListFieldSelect
          options={fieldOptions}
          placeholder={t('dashboard.cardListSelectField')}
          hint={duplicateHint(cardList?.descriptionField, 'description')}
        />
      </Form.Item>

      <div className="mt-5 mb-2 font-medium">{t('dashboard.cardListOptional')}</div>
      <div className="flex flex-col gap-3">
        <OptionalGroup
          title={t('dashboard.cardListAddLeading')}
          open={leadingOpen}
          expandLabel={t('dashboard.cardListExpand')}
          collapseLabel={t('dashboard.cardListCollapse')}
          testId="card-list-optional-leading"
          required={cardList?.leading?.type === 'field'}
          onToggle={() => setLeadingOpen((open) => !open)}
        >
          <Form.Item
            name={['cardList', 'leading', 'type']}
            className={cardList?.leading?.type === 'field' ? 'mb-3' : undefined}
          >
            <LeadingTypeSegmented
              noneLabel={t('dashboard.cardListLeadingNone')}
              indexLabel={t('dashboard.cardListLeadingIndex')}
              fieldLabel={t('dashboard.cardListLeadingField')}
              onClearField={() =>
                form.setFieldValue(['cardList', 'leading', 'field'], undefined)
              }
            />
          </Form.Item>
          {cardList?.leading?.type === 'field' ? (
            <Form.Item
              name={['cardList', 'leading', 'field']}
              required
              rules={[
                {
                  required: true,
                  message: t('dashboard.cardListLeadingFieldRequired'),
                },
              ]}
            >
              <CardListFieldSelect
                allowClear={false}
                options={fieldOptions}
                placeholder={t('dashboard.cardListSelectField')}
                hint={duplicateHint(cardList?.leading?.field, 'leading')}
              />
            </Form.Item>
          ) : null}
        </OptionalGroup>

        <OptionalGroup
          title={t('dashboard.cardListAddBadge')}
          open={badgeOpen}
          expandLabel={t('dashboard.cardListExpand')}
          collapseLabel={t('dashboard.cardListCollapse')}
          testId="card-list-optional-badge"
          tooltip={t('dashboard.cardListBadgeHint')}
          onToggle={() => setBadgeOpen((open) => !open)}
        >
          <Form.Item name={['cardList', 'badgeField']}>
            <CardListFieldSelect
              options={fieldOptions}
              placeholder={t('dashboard.cardListSelectField')}
              hint={duplicateHint(cardList?.badgeField, 'badge')}
            />
          </Form.Item>
        </OptionalGroup>

        <OptionalGroup
          title={t('dashboard.cardListAddTrailing')}
          open={trailingOpen}
          expandLabel={t('dashboard.cardListExpand')}
          collapseLabel={t('dashboard.cardListCollapse')}
          testId="card-list-optional-trailing"
          onToggle={() => setTrailingOpen((open) => !open)}
        >
          <Form.Item
            label={t('dashboard.cardListTrailingFirst')}
            name={['cardList', 'trailingPrimaryField']}
          >
            <CardListFieldSelect
              options={fieldOptions}
              placeholder={t('dashboard.cardListSelectField')}
              hint={duplicateHint(cardList?.trailingPrimaryField, 'trailing')}
            />
          </Form.Item>
          <Form.Item
            label={t('dashboard.cardListTrailingSecond')}
            name={['cardList', 'trailingSecondaryField']}
          >
            <CardListFieldSelect
              options={fieldOptions}
              placeholder={t('dashboard.cardListSelectField')}
            />
          </Form.Item>
        </OptionalGroup>
      </div>

      <div className="mt-5 mb-2 font-medium">{t('dashboard.cardListLayout')}</div>
      <Form.Item name={['cardList', 'layout']} className="mb-0">
        <LayoutPicker
          listLabel={t('dashboard.cardListLayoutList')}
          gridLabel={t('dashboard.cardListLayoutGrid')}
        />
      </Form.Item>
    </div>
  );
};
