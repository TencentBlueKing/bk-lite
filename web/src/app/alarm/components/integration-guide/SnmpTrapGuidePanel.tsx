'use client';

import React from 'react';
import { Form, Select, Steps } from 'antd';
import AlarmIntegrationGuideSectionPanel from '@/app/alarm/components/integration-guide/SectionPanel';
import CompactEmptyState from '@/components/compact-empty-state';

export interface SnmpTrapGuideNodeOption {
  label: React.ReactNode;
  value: string | number;
}

export interface SnmpTrapGuideDetailItem {
  label: React.ReactNode;
  value: React.ReactNode;
  bordered?: boolean;
}

export interface SnmpTrapGuideStep {
  key: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  details?: SnmpTrapGuideDetailItem[];
}

export interface SnmpTrapGuidePanelProps {
  nodeLabel: React.ReactNode;
  nodeHint?: React.ReactNode;
  nodePlaceholder?: string;
  nodeOptions: SnmpTrapGuideNodeOption[];
  selectedNodeId?: string | number;
  loading?: boolean;
  onNodeChange: (value: string | number) => void;
  emptyDescription?: React.ReactNode;
  guideTitle: React.ReactNode;
  steps: SnmpTrapGuideStep[];
  maxHeightClassName?: string;
}

export default function SnmpTrapGuidePanel({
  nodeLabel,
  nodeHint,
  nodePlaceholder,
  nodeOptions,
  selectedNodeId,
  loading = false,
  onNodeChange,
  emptyDescription,
  guideTitle,
  steps,
  maxHeightClassName = 'max-h-[calc(100vh-330px)]',
}: SnmpTrapGuidePanelProps) {
  return (
    <div className={`w-full overflow-y-auto px-[10px] py-4 ${maxHeightClassName}`}>
      <Form name="snmpTrapGuideForm" layout="vertical" className="w-full">
        <Form.Item label={nodeLabel} required>
          <Select
            value={selectedNodeId}
            style={{ width: 600 }}
            className="mr-[10px]"
            placeholder={nodePlaceholder}
            loading={loading}
            onChange={onNodeChange}
            options={nodeOptions}
          />
          {nodeHint ? (
            <span className="text-[12px] text-[var(--color-text-3)]">
              {nodeHint}
            </span>
          ) : null}
        </Form.Item>

        {!loading && nodeOptions.length === 0 ? (
          <CompactEmptyState description={emptyDescription} className="py-4" />
        ) : null}

        {steps.length > 0 ? (
          <AlarmIntegrationGuideSectionPanel
            className="w-full rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]"
            title={guideTitle}
            bodyClassName="px-5 py-4"
          >
            <Steps
              direction="vertical"
              current={Math.max(steps.length - 1, 0)}
              items={steps.map((step) => ({
                key: step.key,
                status: 'process' as const,
                title: step.title,
                description: (
                  <div>
                    {step.description ? (
                      <div className="mb-[10px] text-[12px] leading-5 text-[var(--color-text-3)]">
                        {step.description}
                      </div>
                    ) : null}
                    {step.details?.length ? (
                      <div className="mt-[10px] overflow-hidden rounded-[14px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-3">
                        {step.details.map((detail, index) => {
                          const showDivider =
                            detail.bordered ?? index < step.details!.length - 1;

                          return (
                            <div
                              key={`${step.key}-${index}`}
                              className={showDivider ? 'mb-[10px] border-b border-[var(--color-border-1)] pb-[10px]' : undefined}
                            >
                              <span className="text-[12px] leading-5 text-[var(--color-text-3)]">
                                {detail.label}:
                              </span>
                              <span className="ml-[10px] break-all font-mono font-semibold text-[13px] leading-5 text-[var(--color-primary)]">
                                {detail.value}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                ),
              }))}
            />
          </AlarmIntegrationGuideSectionPanel>
        ) : null}
      </Form>
    </div>
  );
}
