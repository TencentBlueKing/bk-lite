'use client';

import React, { useMemo } from 'react';
import { Alert, Button } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';
import AlarmIntegrationGuideCredentialsPanel from '@/app/alarm/components/integration-guide/CredentialsPanel';
import AlarmIntegrationGuideSectionPanel from '@/app/alarm/components/integration-guide/SectionPanel';
import CompactEmptyState from '@/components/compact-empty-state';
import CodeSnippet from '@/components/code-snippet';
import DetailListPanel from '@/components/detail-list-panel';
import GuideStepPanel from '@/components/guide-step-panel';
import NoteListPanel from '@/components/note-list-panel';
import TroubleshootingCard from '@/components/troubleshooting-card';
import {
  AlertSourceIntegrationGuide,
  IntegrationGuideFieldMappingItem,
  IntegrationGuideParameterMappingItem,
  IntegrationGuideStepItem,
  IntegrationGuideTroubleshootingItem,
  IntegrationGuideVerificationCheck,
} from '@/app/alarm/types/integration-guide';

interface ZabbixGuideProps {
  guide?: AlertSourceIntegrationGuide;
  credentialsSlot?: React.ReactNode;
  selectedTeamSecret?: string;
}

const sectionBodyClassName = 'px-5 py-4';
const cardClassName = 'rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-3.5';

const zabbixParameterDefaults = {
  URL: 'guide.webhook_url',
  SECRET: 'guide.headers.SECRET',
  SOURCE_ID: 'guide.source_id',
  Subject: '{ALERT.SUBJECT}',
  Message: '{ALERT.MESSAGE}',
  Severity: '{EVENT.NSEVERITY}',
  TriggerName: '{TRIGGER.NAME}',
  ProblemId: '{EVENT.ID}',
  EventId: '{EVENT.ID}',
  RecoveryEventId: '{EVENT.RECOVERY.ID}',
  TriggerId: '{TRIGGER.ID}',
  HostId: '{HOST.ID}',
  HostName: '{HOST.NAME}',
  EventValue: '{EVENT.VALUE}',
  ResourceType: 'host',
} as const;

const zabbixParameterAliases: Record<string, keyof typeof zabbixParameterDefaults> = {
  webhook_url: 'URL',
  url: 'URL',
  secret: 'SECRET',
  source_id: 'SOURCE_ID',
};

interface ZabbixParameterRow {
  key: string;
  name: string;
  value: string;
  displayValue: string;
  description?: string;
  required?: boolean;
  copyable?: boolean;
}

const normalizeLegacyStepItem = (item: string | IntegrationGuideStepItem, index: number) => {
  if (typeof item === 'string') {
    return {
      key: `${index}-${item}`,
      title: item,
      description: '',
      content: '',
    };
  }

  return {
    key: `${index}-${item.title || item.description || item.content || 'item'}`,
    title: item.title || '',
    description: item.description || '',
    content: item.content || '',
  };
};

const normalizeTroubleshootingItem = (
  item: IntegrationGuideTroubleshootingItem | string | IntegrationGuideStepItem,
  index: number,
) => {
  if (typeof item === 'string') {
    return {
      key: `${index}-${item}`,
      symptom: item,
      causes: [],
      resolutions: [],
    };
  }

  if ('title' in item || 'description' in item || 'content' in item) {
    return {
      key: `${index}-${item.title || item.description || item.content || 'item'}`,
      symptom: item.title || item.description || '',
      causes: item.content ? [item.content] : [],
      resolutions: [],
    };
  }

  const troubleshootingItem = item as IntegrationGuideTroubleshootingItem;

  return {
    key: `${index}-${troubleshootingItem.symptom || troubleshootingItem.cause || troubleshootingItem.action || 'issue'}`,
    symptom: troubleshootingItem.symptom || '',
    causes: troubleshootingItem.possible_causes?.length
      ? troubleshootingItem.possible_causes
      : troubleshootingItem.cause
        ? [troubleshootingItem.cause]
        : [],
    resolutions: troubleshootingItem.resolutions?.length
      ? troubleshootingItem.resolutions
      : troubleshootingItem.action
        ? [troubleshootingItem.action]
        : [],
  };
};

const renderCheckContent = (check?: IntegrationGuideVerificationCheck) => {
  if (!check) {
    return null;
  }

  return (
    <>
      {check.summary ? (
        <div className="text-[12px] leading-5 text-[var(--color-text-2)]">{check.summary}</div>
      ) : null}
      {check.steps?.length ? (
        <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
          {check.steps.map((step, index) => (
            <li key={`${step}-${index}`} className="flex gap-2">
              <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
              <span>{step}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {check.expected_results?.length ? (
        <div className="mt-3 rounded-[14px] border border-[color-mix(in_srgb,var(--color-success)_18%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-success)_8%,var(--color-bg-1))] px-3.5 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-success)]">
            Expected results
          </div>
          <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
            {check.expected_results.map((result, index) => (
              <li key={`${result}-${index}`} className="flex gap-2">
                <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-success)]" />
                <span>{result}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
};

const ZabbixGuide: React.FC<ZabbixGuideProps> = ({ guide, credentialsSlot, selectedTeamSecret }) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  const sourceSecret = guide?.headers?.SECRET ? String(guide.headers.SECRET) : '';
  const effectiveSecret = selectedTeamSecret || '';
  const secretMasked = effectiveSecret ? '******************' : '';
  const secretPlaceholder = '<' + t('integration.selectTeamPlaceholder') + '>';
  const applyTeamSecret = (raw?: string) => {
    if (!raw) return raw || '';
    if (!effectiveSecret || !sourceSecret) return raw;
    return raw.split(sourceSecret).join(effectiveSecret);
  };

  const sourceWebhookUrl = guide?.webhook_url ? String(guide.webhook_url) : '';
  const browserOrigin = typeof window !== 'undefined' ? window.location.origin : '';
  const applyBrowserOrigin = (rawUrl?: string): string => {
    if (!rawUrl) return '';
    if (!browserOrigin) return rawUrl;
    try {
      const u = new URL(rawUrl);
      return `${browserOrigin}${u.pathname}${u.search}${u.hash}`;
    } catch {
      return rawUrl;
    }
  };
  const effectiveWebhookUrl = applyBrowserOrigin(sourceWebhookUrl);
  const applyEffectiveWebhookUrl = (raw?: string) => {
    if (!raw) return raw || '';
    if (!sourceWebhookUrl || !effectiveWebhookUrl) return raw;
    return raw.split(sourceWebhookUrl).join(effectiveWebhookUrl);
  };

  const setupSteps = useMemo(() => {
    if (guide?.setup_steps?.length) {
      return guide.setup_steps.map((step, index) => ({
        key: `${index}-${step.title || 'step'}`,
        title: step.title || t('integration.zabbixUnnamedStep'),
        items: step.items || [],
      }));
    }

    return (guide?.steps || []).map((item, index) => {
      const normalized = normalizeLegacyStepItem(item, index);
      return {
        key: normalized.key,
        title: normalized.title || t('integration.zabbixUnnamedStep'),
        items: [normalized.description, normalized.content].filter(Boolean),
      };
    });
  }, [guide?.setup_steps, guide?.steps, t]);

  const parameterGuidance = useMemo(() => {
    if (guide?.parameter_guidance?.length) {
      return guide.parameter_guidance;
    }

    if (guide?.parameter_mapping?.length) {
      return guide.parameter_mapping;
    }

    return (guide?.media_type_parameters || []).map<IntegrationGuideParameterMappingItem>((parameter) => ({
      parameter,
    }));
  }, [guide?.media_type_parameters, guide?.parameter_guidance, guide?.parameter_mapping]);

  const parameterRows = useMemo<ZabbixParameterRow[]>(() => {
    const guidanceMap = new Map<string, IntegrationGuideParameterMappingItem>();

    parameterGuidance.forEach((item) => {
      const rawName = item.name || item.parameter || item.field || '';
      const normalizedName = zabbixParameterAliases[rawName] || rawName;

      if (!normalizedName || !(normalizedName in zabbixParameterDefaults)) {
        return;
      }

      guidanceMap.set(normalizedName, item);
    });

    return Object.entries(zabbixParameterDefaults).map(([name, fallbackValue]) => {
      const guidance = guidanceMap.get(name);
      let value = guidance?.value?.trim();

      if (!value) {
        if (name === 'URL') {
          value = effectiveWebhookUrl;
        } else if (name === 'SECRET') {
          value = effectiveSecret;
        } else if (name === 'SOURCE_ID') {
          value = guide?.source_id || '';
        } else {
          value = fallbackValue;
        }
      } else if (name === 'SECRET' && effectiveSecret && sourceSecret && value.includes(sourceSecret)) {
        value = value.split(sourceSecret).join(effectiveSecret);
      } else if (name === 'URL' && sourceWebhookUrl && value.includes(sourceWebhookUrl)) {
        value = value.split(sourceWebhookUrl).join(effectiveWebhookUrl);
      }

      const isSecretRow = name === 'SECRET';
      const displayValue = isSecretRow
        ? (effectiveSecret ? '******************' : secretPlaceholder)
        : value;

      return {
        key: name,
        name,
        value,
        displayValue,
        description: guidance?.description,
        required: guidance?.required,
        copyable: isSecretRow ? Boolean(effectiveSecret) : Boolean(value),
      };
    });
  }, [guide?.headers, guide?.source_id, guide?.webhook_url, parameterGuidance, effectiveSecret, sourceSecret, secretPlaceholder, effectiveWebhookUrl, sourceWebhookUrl]);

  const fieldMappings = useMemo(() => {
    if (guide?.field_mappings?.length) {
      return guide.field_mappings;
    }

    return (guide?.parameter_mapping || []).map<IntegrationGuideFieldMappingItem>((item) => ({
      bk_lite_field: item.target_field || item.field,
      upstream_source: item.parameter || item.name || item.value,
    }));
  }, [guide?.field_mappings, guide?.parameter_mapping]);

  const troubleshootingItems = useMemo(
    () => (guide?.troubleshooting || []).map(normalizeTroubleshootingItem),
    [guide?.troubleshooting]
  );

  const verificationCards = useMemo(() => {
    if (Array.isArray(guide?.verification)) {
      return guide.verification.map((item, index) => {
        const normalized = normalizeLegacyStepItem(item, index);
        return {
          key: normalized.key,
          title: normalized.title || t('integration.zabbixCheckItem'),
          check: {
            summary: normalized.description,
            steps: normalized.content ? [normalized.content] : [],
          } as IntegrationGuideVerificationCheck,
        };
      });
    }

    const verification = guide?.verification;
    return [
      {
        key: 'curl-check',
        title: verification?.curl_check?.title || t('integration.zabbixCurlCheck'),
        check: verification?.curl_check,
      },
      {
        key: 'problem-check',
        title: verification?.problem_check?.title || t('integration.zabbixProblemCheck'),
        check: verification?.problem_check,
      },
      {
        key: 'recovery-check',
        title: verification?.recovery_check?.title || t('integration.zabbixRecoveryCheck'),
        check: verification?.recovery_check,
      },
    ].filter((item) => item.check);
  }, [guide?.verification, t]);

  if (!guide) {
    return <CompactEmptyState description={t('common.noData')} className="py-6" />;
  }

  const descriptionItems = [
    {
      key: 'webhook-url',
      label: t('integration.zabbixWebhookUrl'),
      value: effectiveWebhookUrl,
      display: effectiveWebhookUrl,
      copyable: true,
      masked: false,
    },
    {
      key: 'source-id',
      label: t('integration.zabbixSourceId'),
      value: guide.source_id ? String(guide.source_id) : '',
      display: guide.source_id ? String(guide.source_id) : '',
      copyable: true,
      masked: false,
    },
    {
      key: 'secret-header',
      label: t('integration.zabbixSecretHeader'),
      value: effectiveSecret,
      display: effectiveSecret ? secretMasked : secretPlaceholder,
      copyable: !!effectiveSecret,
      masked: true,
    },
  ].filter((item) => item.masked || item.value);

  return (
    <div className="space-y-4 px-[10px] py-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      {credentialsSlot ? (
        <AlarmIntegrationGuideCredentialsPanel
          title={t('integration.credentialsAndExamples')}
          className="overflow-hidden rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]"
          headerClassName="border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_3%,var(--color-bg-1))] px-5 py-4"
          bodyClassName={sectionBodyClassName}
        >
          {credentialsSlot}
        </AlarmIntegrationGuideCredentialsPanel>
      ) : null}

      {guide.description ? (
        <Alert
          type="info"
          showIcon
          className="rounded-[18px] border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_4%,var(--color-bg-1))]"
          message={t('integration.zabbixGuideOverview')}
          description={<span className="text-[13px] leading-6 text-[var(--color-text-2)]">{guide.description}</span>}
        />
      ) : null}

      {guide.key_reminders?.length ? (
        <AlarmIntegrationGuideSectionPanel
          bodyClassName={`${sectionBodyClassName} space-y-2`}
          title={t('integration.zabbixKeyReminders')}
        >
          <NoteListPanel
            items={guide.key_reminders}
            itemClassName="rounded-[14px] bg-[var(--color-fill-1)] px-3.5 py-3 text-[12px] leading-5"
            bulletClassName="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]"
            textClassName=""
          />
        </AlarmIntegrationGuideSectionPanel>
      ) : null}

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={sectionBodyClassName}
        title={t('integration.zabbixConnectionValues')}
        description={t('integration.zabbixConnectionValuesHelp')}
      >
        <DetailListPanel
          className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
          labelWidthClassName="w-40"
          items={[
            ...descriptionItems.map((item) => ({
              key: item.key,
              label: item.label,
              value: item.value || '',
              displayValue: item.display,
              copyValue: item.value || '',
              copyable: item.copyable,
            })),
            ...Object.entries(guide.headers || {})
              .filter(([key]) => key !== 'SECRET')
              .map(([key, value]) => ({
                key,
                label: `${t('integration.headers')} · ${key}`,
                value: String(value || ''),
                copyValue: String(value || ''),
                copyable: true,
              })),
          ]}
        />
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={sectionBodyClassName}
        title={t('integration.zabbixParameterMapping')}
        description={t('integration.zabbixParameterMappingHelp')}
      >
          {parameterRows.length ? (
            <div className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]">
              <div className="grid grid-cols-[minmax(160px,220px)_minmax(0,1fr)] border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_4%,var(--color-fill-1))]">
                <div className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {t('common.name')}
                </div>
                <div className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {t('common.value')}
                </div>
              </div>
              {parameterRows.map((item, index) => (
                <div
                  key={item.key}
                  className={`grid grid-cols-[minmax(160px,220px)_minmax(0,1fr)] ${index !== parameterRows.length - 1 ? 'border-b border-[var(--color-border-1)]' : ''}`}
                >
                  <div className="flex flex-col gap-1 px-4 py-3">
                    <span className="font-mono text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{item.name}</span>
                    {item.required !== undefined ? (
                      <span className={`text-[11px] font-medium leading-4 ${item.required ? 'text-[var(--color-error)]' : 'text-[var(--color-text-3)]'}`}>
                        {item.required ? t('common.required') : t('integration.zabbixOptional')}
                      </span>
                    ) : null}
                  </div>
                  <div className="min-w-0 px-4 py-3">
                    <div className="flex min-w-0 items-start gap-2">
                      <span className={`min-w-0 flex-1 break-all font-mono text-[13px] leading-6 ${item.copyable ? 'text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`}>
                        {item.displayValue || '--'}
                      </span>
                      {item.copyable ? (
                        <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(item.value)} />
                      ) : null}
                    </div>
                    {item.description ? (
                      <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-2)]">{item.description}</div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : <CompactEmptyState description={t('common.noData')} />}
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={`${sectionBodyClassName} space-y-3`}
        title={t('integration.eventFieldsMapping')}
      >
          {fieldMappings.length ? fieldMappings.map((item, index) => (
            <div key={`${item.bk_lite_field || 'field'}-${index}`} className={cardClassName}>
              <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                {t('integration.zabbixMapsTo')}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-mono text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">
                  {item.bk_lite_field || '--'}
                </span>
                <span className="text-[var(--color-text-3)]">←</span>
                <span className="text-[13px] leading-6 text-[var(--color-text-2)] break-all">
                  {item.upstream_source || item.zabbix_field || '--'}
                </span>
              </div>
            </div>
          )) : <CompactEmptyState description={t('common.noData')} />}
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={sectionBodyClassName}
        title={t('integration.zabbixScriptTemplate')}
        description={t('integration.zabbixScriptTemplateHelp')}
      >
          {guide.script_template ? (
            <CodeSnippet
              value={applyEffectiveWebhookUrl(applyTeamSecret(guide.script_template))}
              copyable
              copyDisabled={!effectiveSecret}
            />
          ) : (
            <CompactEmptyState description={t('common.noData')} />
          )}
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={`${sectionBodyClassName} space-y-3`}
        title={t('integration.deploySteps')}
      >
          {setupSteps.length ? setupSteps.map((step, index) => (
            <GuideStepPanel
              key={step.key}
              step={index + 1}
              title={step.title}
              className="mb-0"
              cardClassName={cardClassName}
            >
              {step.items.length ? (
                <ul className="space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
                  {step.items.map((item, itemIndex) => (
                    <li key={`${item}-${itemIndex}`} className="flex gap-2">
                      <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </GuideStepPanel>
          )) : <CompactEmptyState description={t('common.noData')} />}
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={`${sectionBodyClassName} grid gap-3 xl:grid-cols-3`}
        title={t('integration.verifyResult')}
      >
          {verificationCards.length ? verificationCards.map((item) => (
            <div key={item.key} className={cardClassName}>
              <div className="text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{item.title}</div>
              <div className="mt-2">{renderCheckContent(item.check)}</div>
            </div>
          )) : <CompactEmptyState description={t('common.noData')} />}
      </AlarmIntegrationGuideSectionPanel>

      <AlarmIntegrationGuideSectionPanel
        bodyClassName={`${sectionBodyClassName} space-y-3`}
        title={t('integration.zabbixTroubleshooting')}
      >
          {troubleshootingItems.length ? troubleshootingItems.map((item) => (
            <TroubleshootingCard
              key={item.key}
              title={item.symptom || t('integration.zabbixCheckItem')}
              causeLabel={t('integration.zabbixPossibleCauses')}
              causes={item.causes}
              solutionLabel={t('integration.zabbixResolutions')}
              solutions={item.resolutions}
              solutionTone="accent"
              cardClassName={cardClassName}
            />
          )) : <CompactEmptyState description={t('common.noData')} />}
      </AlarmIntegrationGuideSectionPanel>
    </div>
  );
};

export default ZabbixGuide;
