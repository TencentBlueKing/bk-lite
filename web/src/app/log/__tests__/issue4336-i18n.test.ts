import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createIntl, createIntlCache } from 'react-intl';
import { describe, expect, it } from 'vitest';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';

interface NestedMessages {
  [key: string]: string | NestedMessages;
}

function flattenMessages(nested: NestedMessages, prefix = ''): Record<string, string> {
  return Object.keys(nested).reduce<Record<string, string>>((messages, key) => {
    const value = nested[key];
    const messageKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      messages[messageKey] = value;
    } else {
      Object.assign(messages, flattenMessages(value, messageKey));
    }
    return messages;
  }, {});
}

const zhMessages = flattenMessages(zh as NestedMessages);
const enMessages = flattenMessages(en as NestedMessages);

const keys = [
  'log.analysis.unknownComponent',
  'log.analysis.comparedWithPrevious',
  'log.analysis.total',
  'common.searchPlaceHolder',
];

function readSource(relativePath: string): string {
  return readFileSync(path.join(process.cwd(), relativePath), 'utf8');
}

describe('log issue 4336 confirmed copy', () => {
  it('resolves the dashboard labels in both languages', () => {
    for (const key of keys) {
      expect(zhMessages[key], key).toBeTruthy();
      expect(enMessages[key], key).toBeTruthy();
      expect(zhMessages[key]).not.toBe(enMessages[key]);
    }
    expect(zhMessages['log.analysis.total']).toBe('总数');
    expect(enMessages['log.analysis.total']).toBe('Total');
    expect(zhMessages['common.searchPlaceHolder']).toBe('搜索...');
    expect(enMessages['common.searchPlaceHolder']).toBe('Search...');
  });

  it('formats the unknown component label with the chart type', () => {
    const intl = createIntl(
      { locale: 'en', messages: { 'log.analysis.unknownComponent': enMessages['log.analysis.unknownComponent'] } },
      createIntlCache()
    );
    expect(intl.formatMessage({ id: 'log.analysis.unknownComponent' }, { chartType: 'gauge' })).toBe(
      'Unknown component type: gauge'
    );
  });

  it('reads those labels through t() at the confirmed call sites', () => {
    const sources = [
      'src/app/log/(pages)/analysis/dashBoard/components/widgetWrapper.tsx',
      'src/app/log/(pages)/analysis/dashBoard/widgets/comKpiCard.tsx',
      'src/app/log/(pages)/analysis/dashBoard/widgets/docker/dockerDonutChart.tsx',
      'src/app/log/(pages)/analysis/page.tsx',
      'src/app/log/components/log-donut-chart/index.tsx',
      'src/app/log/components/log-kpi-card/index.tsx',
    ].map(readSource);

    expect(sources[0]).toContain("t('log.analysis.unknownComponent'");
    expect(sources[1]).toContain("t('log.analysis.comparedWithPrevious'");
    expect(sources[2]).toContain("t('log.analysis.total'");
    expect(sources[3]).toContain("t('common.searchPlaceHolder'");
    expect(sources[4]).toContain("t('log.analysis.total'");
    expect(sources[5]).toContain("t('log.analysis.comparedWithPrevious'");
    for (const source of sources) {
      expect(source).not.toContain('>较上一周期<');
      expect(source).not.toContain('>总数<');
      expect(source).not.toContain('placeholder="搜索..."');
    }
  });

  it('formats literal brackets and variable syntax instead of the key', () => {
    const i18nSource = readSource('src/utils/i18n.ts');
    expect(i18nSource).toContain(`catalogMessage.includes("'<'")`);
    expect(i18nSource).toContain(`catalogMessage.includes("'>'")`);

    const expected = {
      en: {
        'log.extractor.regexNamedGroupHint':
          'Include at least one named capture group, for example (?P<status>\\d+). Capture names become output fields.',
        'log.integration.k8s.commonIssuePendingSolution2':
          'Check scheduling events for the DaemonSet/Pod: kubectl describe pod <pod-name> -n bk-lite-collector',
        'log.integration.k8s.commonIssueMountSolution2':
          'Inspect the collector container: kubectl exec -it -n bk-lite-collector <vector-pod> -- sh, then verify /etc/vector/vector.yaml and the target log directory exist.',
        'log.integration.kafkaSubscribeGroupHint':
          "Kafka consumer group ID. Leave empty to use bk-lite-<instance ID>. Do not reuse a group already used by the customer's consumers.",
        'log.integration.kafkaSubscribeGroupPlaceholder':
          'Leave empty to use bk-lite-<instance ID>',
        'log.event.variableUsageTips':
          'Group fields automatically become ${log.fieldName} variables. ${level} is always available.',
      },
      zh: {
        'log.extractor.regexNamedGroupHint':
          '至少需要一个命名捕获组，例如 (?P<status>\\d+)，捕获组名就是写出的字段名。',
        'log.integration.k8s.commonIssuePendingSolution2':
          '检查 DaemonSet/Pod 的调度事件：kubectl describe pod <pod-name> -n bk-lite-collector',
        'log.integration.k8s.commonIssueMountSolution2':
          '进入采集器容器检查挂载和配置：kubectl exec -it -n bk-lite-collector <vector-pod> -- sh，然后确认 /etc/vector/vector.yaml 与目标日志目录存在。',
        'log.integration.kafkaSubscribeGroupHint':
          'Kafka 消费组 ID。留空时使用 bk-lite-<实例ID>。不要占用客户现有消费者使用的组名。',
        'log.integration.kafkaSubscribeGroupPlaceholder': '留空则使用 bk-lite-<实例ID>',
        'log.event.variableUsageTips':
          '分组字段会自动变成 ${log.fieldName} 变量，告警级别可用 ${level}。',
      },
    };

    (['en', 'zh'] as const).forEach((locale) => {
      const messages = locale === 'en' ? enMessages : zhMessages;
      Object.entries(expected[locale]).forEach(([key, visible]) => {
        const message = messages[key];
        const needsFullIcu =
          message.includes("'{'") ||
          message.includes("'}'") ||
          message.includes("'<'") ||
          message.includes("'>'");
        const intl = createIntl({ locale, messages: { [key]: message } }, createIntlCache());
        expect(intl.formatMessage({ id: key }, needsFullIcu ? {} : undefined), key).toBe(visible);
        expect(visible, key).not.toBe(key);
      });
    });
  });

  it('uses the shared total label in pie centers', () => {
    const pies = [
      'src/app/log/(pages)/analysis/dashBoard/widgets/comPie.tsx',
      'src/app/log/components/log-analysis-widgets/pie.tsx',
    ].map(readSource);
    for (const source of pies) {
      expect(source).toContain("t('log.analysis.total')");
      expect(source).toContain('{title|${totalLabel}}');
      expect(source).not.toContain('{title|总数}');
    }
  });
});
