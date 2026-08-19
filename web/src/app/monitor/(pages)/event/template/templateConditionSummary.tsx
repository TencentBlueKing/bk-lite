'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  formatTemplateAlgorithmSummary,
  getTemplateThresholdItems,
  getTemplateTriggerCount,
  BulkConfig,
  PolicyTemplateItem,
} from './templateBulkUtils';
import templateStyle from './index.module.scss';

interface TemplateConditionSummaryProps {
  template: PolicyTemplateItem;
  config?: BulkConfig;
}

const TemplateConditionSummary: React.FC<TemplateConditionSummaryProps> = ({
  template,
  config,
}) => {
  const { t } = useTranslation();
  const thresholds = getTemplateThresholdItems(template);
  const algorithm = formatTemplateAlgorithmSummary(template);
  const triggerCount = getTemplateTriggerCount(template, config?.trigger_count);
  const trigger = t('monitor.events.consecutiveTrigger', '连续 {count} 个周期触发', {
    count: triggerCount,
  });
  const thresholdTitle = thresholds
    .map((item) => {
      const level = t(`monitor.events.${item.level}`, item.label);
      return `${level} ${item.method} ${item.value}${item.unitSuffix}`;
    })
    .join('；');

  const renderThresholds = () => {
    if (thresholds.length) {
      return (
        <span className={templateStyle.thresholdTextList}>
          {thresholds.map((item, index) => (
            <React.Fragment key={`${item.level}-${item.method}-${String(item.value)}`}>
              {index > 0 && <span className={templateStyle.conditionSep}>；</span>}
              <span className={templateStyle.thresholdTextItem}>
                <span className={templateStyle.thresholdLevelText} style={{ color: item.color }}>
                  {t(`monitor.events.${item.level}`, item.label)}
                </span>
                <span className={templateStyle.thresholdValueText}>
                  {item.method} {item.value}
                  {item.unitSuffix}
                </span>
              </span>
            </React.Fragment>
          ))}
        </span>
      );
    }
    if (template.query_condition?.type === 'pmq') {
      return t('monitor.events.trapQueryAlert', 'Trap 查询告警');
    }
    return '--';
  };

  return (
    <div className={templateStyle.conditionSummary}>
      {algorithm ? (
        <div className={templateStyle.conditionRow}>
          <span className={templateStyle.conditionLabel}>
            {t('monitor.events.convergenceMethod', '汇聚方式')}：
          </span>
          <span className={templateStyle.conditionContent} title={algorithm}>{algorithm}</span>
        </div>
      ) : null}
      <div className={templateStyle.conditionRow}>
        <span className={templateStyle.conditionLabel}>
          {t('monitor.events.alertCondition', '告警条件')}：
        </span>
        <span className={templateStyle.conditionContent} title={`${thresholdTitle}${trigger ? `；${trigger}` : ''}`}>
          {renderThresholds()}
          {trigger ? (
            <>
              <span className={templateStyle.conditionSep}>；</span>
              <span>{trigger}</span>
            </>
          ) : null}
        </span>
      </div>
    </div>
  );
};

export default TemplateConditionSummary;
