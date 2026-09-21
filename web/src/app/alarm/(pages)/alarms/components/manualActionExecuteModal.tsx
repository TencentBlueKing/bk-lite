'use client';

import { Input, Modal } from 'antd';
import { ActionRuleListItem } from '@/app/alarm/types/settings';
import { adjustableConstBindings } from '@/app/alarm/utils/actionParamBindings';

export async function runManualActionTrigger(options: {
  alertId: string;
  rule: Pick<ActionRuleListItem, 'id' | 'action_config' | 'name'>;
  trigger: (body: {
    alert_id: string;
    rule_id: number;
    param_overrides?: Record<string, string>;
  }) => Promise<unknown>;
  t: (key: string, fallback?: string) => string;
}): Promise<'cancelled' | 'triggered'> {
  const { alertId, rule, trigger, t } = options;
  const adjustable = adjustableConstBindings(rule.action_config?.param_bindings || []);

  if (adjustable.length === 0) {
    await trigger({ alert_id: alertId, rule_id: rule.id });
    return 'triggered';
  }

  const edited: Record<string, string> = Object.fromEntries(
    adjustable.map((binding) => [binding.name, binding.value])
  );

  return new Promise((resolve) => {
    Modal.confirm({
      title: t('settings.actionExecuteParams'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      content: (
        <div className="flex flex-col gap-3">
          <div className="text-sm text-[var(--color-text-3)]">
            {t('settings.actionExecuteParamsTip')}
          </div>
          {adjustable.map((binding) => (
            <div key={binding.name}>
              <div className="mb-1">{binding.name}</div>
              <Input
                defaultValue={binding.value}
                onChange={(event) => {
                  edited[binding.name] = event.target.value;
                }}
              />
            </div>
          ))}
        </div>
      ),
      onOk: async () => {
        await trigger({
          alert_id: alertId,
          rule_id: rule.id,
          param_overrides: edited,
        });
        resolve('triggered');
      },
      onCancel: () => resolve('cancelled'),
    });
  });
}
