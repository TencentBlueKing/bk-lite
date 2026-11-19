import React, { useEffect, useMemo, useState } from 'react';
import {
  DownOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Form, Radio, Select, Tooltip } from 'antd';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import {
  normalizeCardListAccentStyle,
  type CardListAccentStyle,
} from '@/app/ops-analysis/utils/cardList';
import { CardListAccentStyleModal } from './cardListAccentStyleModal';
import {
  buildCardListFieldOptions,
  getCardListDuplicateHintSlots,
  resolveCardListOptionalOpenState,
  resolveCardListOptionalSummaries,
  type CardListFormState,
} from '../utils/cardListSettingsModel';
import { ConfigSectionTitle } from '../configTitles';
import { ChartRoleLabel, RefreshFieldsButton } from './chartRoleLabel';

interface CardListSettingsSectionProps {
  t: (
    key: string,
    defaultMessage?: string,
    values?: Record<string, string | number>,
  ) => string;
  availableFields: ResponseFieldDefinition[];
  previewRawData?: unknown;
  loadingFields?: boolean;
  onRefreshFields?: () => void;
  /** 关闭再打开或换一条配置时变化，用来按当前草稿重算展开。 */
  resetToken?: string;
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
  onUserEdit,
  testId,
  invalidName,
  revealClosedLeading,
}: {
  options: ReturnType<typeof buildCardListFieldOptions>;
  placeholder: string;
  hint?: string;
  allowClear?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  onUserEdit?: () => void;
  testId?: string;
  invalidName?: (string | number)[];
  revealClosedLeading?: { open: boolean; onInvalid: () => void };
}) => (
  <>
    {invalidName ? <ScrollWhenInvalid name={invalidName} /> : null}
    {revealClosedLeading ? (
      <LeadingErrorReveal
        open={revealClosedLeading.open}
        onInvalid={revealClosedLeading.onInvalid}
      />
    ) : null}
    <Select
      allowClear={allowClear}
      showSearch
      optionFilterProp="label"
      options={options}
      placeholder={placeholder}
      value={value}
      data-testid={testId}
      onChange={(next) => {
        onUserEdit?.();
        onChange?.(next);
      }}
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
  summary,
  open,
  testId,
  onToggle,
  children,
}: {
  title: string;
  summary: string;
  open: boolean;
  testId: string;
  onToggle: () => void;
  children: React.ReactNode;
}) => (
  <section>
    <button
      type="button"
      aria-expanded={open}
      data-testid={testId}
      className="flex w-full cursor-pointer items-center gap-2 rounded-md py-3 text-left transition-colors duration-150 hover:bg-(--color-fill-1) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
      onClick={onToggle}
    >
      <DownOutlined
        aria-hidden
        data-testid={`${testId}-chevron`}
        className={`shrink-0 text-xs text-(--color-text-3) transition-transform duration-150 ${open ? '' : '-rotate-90'}`}
      />
      <span className="min-w-0 flex-1 truncate text-sm font-medium leading-5 text-(--color-text-1)">
        {title}
      </span>
      <span
        data-testid={`${testId}-summary`}
        hidden={open}
        className="max-w-[45%] shrink-0 truncate text-xs leading-5 text-(--color-text-3)"
      >
        {summary}
      </span>
    </button>
    <div
      data-testid={`${testId}-body`}
      className={open ? 'pb-3 pl-5' : 'hidden'}
      hidden={!open}
    >
      {children}
    </div>
  </section>
);

const FieldLabel = ({
  text,
  tip,
  required = false,
  testId,
}: {
  text: string;
  tip?: string;
  required?: boolean;
  testId?: string;
}) => (
  <span className="inline-flex items-center text-sm leading-5 text-(--color-text-1)" data-testid={testId}>
    {required ? (
      <span className="mr-1 text-[var(--color-fail)]" aria-hidden>
        *
      </span>
    ) : null}
    {tip ? <ChartRoleLabel text={text} tip={tip} /> : text}
  </span>
);

const ScrollWhenInvalid = ({
  name,
}: {
  name: (string | number)[];
}) => {
  const { status } = Form.Item.useStatus();
  const form = Form.useFormInstance();
  useEffect(() => {
    if (status !== 'error') return;
    form.scrollToField(name, { block: 'center' });
  }, [form, name, status]);
  return null;
};

const LeadingErrorReveal = ({
  open,
  onInvalid,
}: {
  open: boolean;
  onInvalid: () => void;
}) => {
  const { status } = Form.Item.useStatus();
  useEffect(() => {
    if (status === 'error' && !open) onInvalid();
  }, [onInvalid, open, status]);
  return null;
};

const LeadingTypeSegmented = ({
  value,
  onChange,
  noneLabel,
  indexLabel,
  fieldLabel,
  onClearField,
  onClearStyle,
  onUserEdit,
}: {
  value?: 'none' | 'index' | 'field';
  onChange?: (value: 'none' | 'index' | 'field') => void;
  noneLabel: string;
  indexLabel: string;
  fieldLabel: string;
  onClearField: () => void;
  onClearStyle: () => void;
  onUserEdit?: () => void;
}) => (
  <Radio.Group
    optionType="button"
    value={value}
    onChange={(event) => {
      onUserEdit?.();
      const typed = event.target.value as 'none' | 'index' | 'field';
      onChange?.(typed);
      if (typed !== 'field') {
        onClearField();
      }
      if (typed === 'none') {
        onClearStyle();
      }
    }}
  >
    <Radio.Button value="none">{noneLabel}</Radio.Button>
    <Radio.Button value="index">{indexLabel}</Radio.Button>
    <Radio.Button value="field">{fieldLabel}</Radio.Button>
  </Radio.Group>
);

const hasAccentStyle = (style?: CardListAccentStyle) =>
  Boolean(normalizeCardListAccentStyle(style));

/** 注册弹窗写入的样式字段，否则 validateFields 不会带上未挂 Form.Item 的值。 */
const StoredAccentStyle = () => (
  <span hidden data-testid="stored-accent-style" />
);

const AccentStyleButton = ({
  t,
  configured,
  testId,
  onClick,
}: {
  t: (key: string) => string;
  configured: boolean;
  testId: string;
  onClick: () => void;
}) => (
  <Tooltip title={t('dashboard.cardListAccentStyleConfig')}>
    <Button
      type="text"
      size="small"
      data-testid={testId}
      icon={<SettingOutlined aria-hidden />}
      aria-label={t('dashboard.cardListAccentStyleConfig')}
      onClick={onClick}
      style={{
        border: 'none',
        padding: '4px',
        color: configured ? 'var(--color-primary)' : 'var(--color-text-2)',
      }}
    />
  </Tooltip>
);

const TITLE_FIELD_NAME = ['cardList', 'titleField'];
const LEADING_FIELD_NAME = ['cardList', 'leading', 'field'];

export const CardListSettingsSection: React.FC<CardListSettingsSectionProps> = ({
  t,
  availableFields,
  previewRawData,
  loadingFields = false,
  onRefreshFields,
  resetToken = 'open',
}) => {
  const form = Form.useFormInstance();
  // 必须分别 watch nested style：useWatch('cardList') 组装出的 leading
  // 可能只有 type/field，浅合并会盖掉 sibling 的 style，导致弹窗回读丢失并在确认时清空。
  const watchedCardList = Form.useWatch('cardList') as CardListFormState | undefined;
  Form.useWatch(['cardList', 'leading']);
  Form.useWatch(['cardList', 'badgeStyle']);
  const cardList: CardListFormState = {
    ...(form.getFieldValue('cardList') || {}),
    ...(watchedCardList || {}),
    leading: form.getFieldValue(['cardList', 'leading']),
    badgeStyle: form.getFieldValue(['cardList', 'badgeStyle']),
  };
  const restored = resolveCardListOptionalOpenState(cardList);
  const [leadingOpen, setLeadingOpen] = useState(restored.leading);
  const [badgeOpen, setBadgeOpen] = useState(restored.badge);
  const [trailingOpen, setTrailingOpen] = useState(restored.trailing);
  const [styleTarget, setStyleTarget] = useState<'leading' | 'badge' | null>(
    null,
  );
  const suspendOpenSync = React.useRef(false);
  const markUserEdited = () => {
    suspendOpenSync.current = true;
  };

  useEffect(() => {
    suspendOpenSync.current = false;
  }, [resetToken]);

  useEffect(() => {
    if (suspendOpenSync.current) return;
    setLeadingOpen(restored.leading);
    setBadgeOpen(restored.badge);
    setTrailingOpen(restored.trailing);
  }, [resetToken, restored.leading, restored.badge, restored.trailing]);

  const revealLeadingError = React.useCallback(() => {
    setLeadingOpen(true);
  }, []);

  useEffect(() => {
    if (!cardList?.badgeField?.trim() && cardList?.badgeStyle) {
      form.setFieldValue(['cardList', 'badgeStyle'], undefined);
    }
  }, [cardList?.badgeField, cardList?.badgeStyle, form]);

  const fieldOptions = useMemo(
    () => buildCardListFieldOptions(availableFields, previewRawData),
    [availableFields, previewRawData],
  );
  const fieldPlaceholder = fieldOptions.length === 0
    ? t('topology.nodeConfig.clickRefreshToGetFields')
    : t('dashboard.cardListSelectField');
  const summaries = resolveCardListOptionalSummaries(cardList, fieldOptions, {
    none: t('dashboard.cardListLeadingNone'),
    index: t('dashboard.cardListLeadingIndex'),
    field: t('dashboard.cardListLeadingField'),
    unconfigured: t('dashboard.cardListUnconfigured'),
    firstLine: t('dashboard.cardListTrailingFirst'),
    secondLine: t('dashboard.cardListTrailingSecond'),
  });

  const duplicateHint = (fieldKey: string | undefined, currentSlot: string) => {
    const slots = getCardListDuplicateHintSlots(fieldKey, cardList, currentSlot);
    if (!slots.length) {
      return undefined;
    }
    return t(
      'dashboard.cardListFieldUsedIn',
      '该字段已用于{slot}',
      {
        slot: slots.map((slot) => t(SLOT_LABEL_KEYS[slot] || slot)).join(' / '),
      },
    );
  };

  const leadingEnabled =
    cardList?.leading?.type === 'index' || cardList?.leading?.type === 'field';
  const badgeEnabled = Boolean(cardList?.badgeField?.trim());

  return (
    <div className="mb-6">
      <Form.Item name={['cardList', 'leading', 'style']} noStyle>
        <StoredAccentStyle />
      </Form.Item>
      <Form.Item name={['cardList', 'badgeStyle']} noStyle>
        <StoredAccentStyle />
      </Form.Item>
      <ConfigSectionTitle
        actions={(
          <RefreshFieldsButton
            label={t('dashboard.refreshFields')}
            loading={loadingFields}
            onClick={onRefreshFields}
          />
        )}
      >
        {t('dashboard.dataFields')}
      </ConfigSectionTitle>

      <div className="space-y-6">
      <div>
      <Form.Item
        label={(
          <ChartRoleLabel
            text={t('dashboard.cardListTitleField')}
            tip={t('dashboard.cardListTitleFieldTip')}
          />
        )}
        labelCol={{ span: 24 }}
        wrapperCol={{ span: 24 }}
        name={['cardList', 'titleField']}
        rules={[{ required: true, message: t('dashboard.cardListTitleRequired') }]}
      >
        <CardListFieldSelect
          options={fieldOptions}
          placeholder={fieldPlaceholder}
          onUserEdit={markUserEdited}
          invalidName={TITLE_FIELD_NAME}
        />
      </Form.Item>
      <Form.Item
        label={(
          <ChartRoleLabel
            text={t('dashboard.cardListDescriptionField')}
            tip={t('dashboard.cardListDescriptionFieldTip')}
          />
        )}
        labelCol={{ span: 24 }}
        wrapperCol={{ span: 24 }}
        className="mb-0"
        name={['cardList', 'descriptionField']}
      >
        <CardListFieldSelect
          options={fieldOptions}
          placeholder={fieldPlaceholder}
          hint={duplicateHint(cardList?.descriptionField, 'description')}
          onUserEdit={markUserEdited}
        />
      </Form.Item>
      </div>

      <div>
      <ConfigSectionTitle>
        {t('dashboard.cardListOptional')}
      </ConfigSectionTitle>
      <div className="divide-y divide-(--color-border-2)">
        <OptionalGroup
          title={t('dashboard.cardListAddLeading')}
          summary={summaries.leading}
          open={leadingOpen}
          testId="card-list-optional-leading"
          onToggle={() => {
            markUserEdited();
            setLeadingOpen((open) => !open);
          }}
        >
          <div className="mb-2">
            <FieldLabel
              text={t('dashboard.cardListDisplayMode')}
              tip={t('dashboard.cardListLeadingFieldTip')}
              testId="card-list-display-mode-label"
            />
          </div>
          <div className="mb-3 flex items-center gap-1">
            <Form.Item
              name={['cardList', 'leading', 'type']}
              className="mb-0 min-w-0 flex-1"
            >
              <LeadingTypeSegmented
                noneLabel={t('dashboard.cardListLeadingNone')}
                indexLabel={t('dashboard.cardListLeadingIndex')}
                fieldLabel={t('dashboard.cardListLeadingField')}
                onUserEdit={markUserEdited}
                onClearField={() =>
                  form.setFieldValue(['cardList', 'leading', 'field'], undefined)
                }
                onClearStyle={() =>
                  form.setFieldValue(['cardList', 'leading', 'style'], undefined)
                }
              />
            </Form.Item>
            {leadingEnabled ? (
              <AccentStyleButton
                t={t}
                configured={hasAccentStyle(cardList?.leading?.style)}
                testId="card-list-leading-style-btn"
                onClick={() => setStyleTarget('leading')}
              />
            ) : null}
          </div>
          {cardList?.leading?.type === 'field' ? (
            <Form.Item
              name={['cardList', 'leading', 'field']}
              className="mb-3"
              label={(
                <FieldLabel
                  text={t('dashboard.cardListBindField')}
                  tip={t('dashboard.cardListLeadingFieldTip')}
                  required
                  testId="card-list-leading-bind-label"
                />
              )}
              labelCol={{ span: 24 }}
              wrapperCol={{ span: 24 }}
              required={false}
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
                placeholder={fieldPlaceholder}
                hint={duplicateHint(cardList?.leading?.field, 'leading')}
                onUserEdit={markUserEdited}
                testId="card-list-leading-field"
                invalidName={LEADING_FIELD_NAME}
                revealClosedLeading={{ open: leadingOpen, onInvalid: revealLeadingError }}
              />
            </Form.Item>
          ) : null}
        </OptionalGroup>

        <OptionalGroup
          title={t('dashboard.cardListAddBadge')}
          summary={summaries.badge}
          open={badgeOpen}
          testId="card-list-optional-badge"
          onToggle={() => {
            markUserEdited();
            setBadgeOpen((open) => !open);
          }}
        >
          <div className="mb-2">
            <FieldLabel
              text={t('dashboard.cardListBindField')}
              tip={t('dashboard.cardListBadgeHint')}
              testId="card-list-badge-field-label"
            />
          </div>
          <div className="mb-3 flex items-start gap-1">
            <Form.Item
              name={['cardList', 'badgeField']}
              className="mb-0 min-w-0 flex-1"
            >
              <CardListFieldSelect
                options={fieldOptions}
                placeholder={fieldPlaceholder}
                hint={duplicateHint(cardList?.badgeField, 'badge')}
                onUserEdit={markUserEdited}
                testId="card-list-badge-field"
              />
            </Form.Item>
            {badgeEnabled ? (
              <AccentStyleButton
                t={t}
                configured={hasAccentStyle(cardList?.badgeStyle)}
                testId="card-list-badge-style-btn"
                onClick={() => setStyleTarget('badge')}
              />
            ) : null}
          </div>
        </OptionalGroup>

        <OptionalGroup
          title={t('dashboard.cardListAddTrailing')}
          summary={summaries.trailing}
          open={trailingOpen}
          testId="card-list-optional-trailing"
          onToggle={() => {
            markUserEdited();
            setTrailingOpen((open) => !open);
          }}
        >
          <Form.Item
            name={['cardList', 'trailingPrimaryField']}
            labelCol={{ span: 24 }}
            wrapperCol={{ span: 24 }}
            label={(
              <FieldLabel
                text={t('dashboard.cardListTrailingFirst')}
                tip={t('dashboard.cardListTrailingFieldTip')}
                testId="card-list-trailing-first-label"
              />
            )}
          >
            <CardListFieldSelect
              options={fieldOptions}
              placeholder={fieldPlaceholder}
              hint={duplicateHint(cardList?.trailingPrimaryField, 'trailing')}
              onUserEdit={markUserEdited}
            />
          </Form.Item>
          <Form.Item
            name={['cardList', 'trailingSecondaryField']}
            labelCol={{ span: 24 }}
            wrapperCol={{ span: 24 }}
            className="mb-3"
            label={(
              <FieldLabel
                text={t('dashboard.cardListTrailingSecond')}
                tip={t('dashboard.cardListTrailingFieldTip')}
                testId="card-list-trailing-second-label"
              />
            )}
          >
            <CardListFieldSelect
              options={fieldOptions}
              placeholder={fieldPlaceholder}
              onUserEdit={markUserEdited}
            />
          </Form.Item>
        </OptionalGroup>
      </div>
      </div>

      <div>
      <ConfigSectionTitle>
        {t('dashboard.cardListLayout')}
      </ConfigSectionTitle>
      <Form.Item name={['cardList', 'layout']} className="mb-0">
        <LayoutPicker
          listLabel={t('dashboard.cardListLayoutList')}
          gridLabel={t('dashboard.cardListLayoutGrid')}
        />
      </Form.Item>
      </div>
      </div>

      {styleTarget ? (
        <CardListAccentStyleModal
          open
          title={`${t('dashboard.cardListAccentStyleConfig')} ${
            styleTarget === 'badge'
              ? t('dashboard.cardListAddBadge')
              : t('dashboard.cardListAddLeading')
          }`}
          value={
            styleTarget === 'badge'
              ? form.getFieldValue(['cardList', 'badgeStyle'])
              : form.getFieldValue(['cardList', 'leading', 'style'])
          }
          t={t}
          onCancel={() => setStyleTarget(null)}
          onConfirm={(nextStyle) => {
            if (styleTarget === 'badge') {
              form.setFieldValue(['cardList', 'badgeStyle'], nextStyle);
            } else {
              form.setFieldValue(['cardList', 'leading', 'style'], nextStyle);
            }
            setStyleTarget(null);
          }}
        />
      ) : null}
    </div>
  );
};
