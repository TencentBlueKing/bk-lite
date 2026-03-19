import React from 'react';
import { Form, Switch, Tooltip, Input, Checkbox } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const levelOptions = [
  { label: 'Critical', value: 'critical' },
  { label: 'Error', value: 'error' },
  { label: 'Warning', value: 'warning' },
  { label: 'Information', value: 'info' }
];

const useWinlogbeatFormItems = () => {
  const { t } = useTranslation();

  const renderLogSection = (
    name: string,
    labelKey: string,
    descKey: string,
    defaultEnabled: boolean,
    disabledFormItems: Record<string, boolean>,
    showEventId?: boolean,
    eventIdHintKey?: string
  ) => {
    return (
      <>
        <Form.Item layout="vertical" className="mb-[8px]">
          <div className="flex items-center">
            <span className="mr-[10px] font-semibold">
              {t(`log.integration.${labelKey}`)}
            </span>
            <Form.Item noStyle name={[name, 'enabled']}>
              <Switch disabled={disabledFormItems[`${name}_enabled`]} />
            </Form.Item>
          </div>
        </Form.Item>
        <div className="text-[var(--color-text-3)] mb-[12px]">
          {t(`log.integration.${descKey}`)}
        </div>
        <Form.Item
          className="mb-[0]"
          shouldUpdate={(prevValues, curValues) =>
            prevValues?.[name]?.enabled !== curValues?.[name]?.enabled
          }
        >
          {({ getFieldValue }) => {
            const enabled = getFieldValue([name, 'enabled']);
            return (
              <div
                className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                  !enabled ? 'hidden' : ''
                }`}
              >
                {enabled && (
                  <>
                    <Form.Item className="mb-[16px]">
                      <div className="flex items-center">
                        <div className="flex items-center w-[100px] mr-[10px]">
                          <span>{t('log.integration.winlogEventLevel')}</span>
                        </div>
                        <Form.Item
                          className="mb-0 flex-1"
                          name={[name, 'level']}
                        >
                          <Checkbox.Group
                            options={levelOptions}
                            disabled={disabledFormItems[`${name}_level`]}
                          />
                        </Form.Item>
                      </div>
                    </Form.Item>
                    {showEventId && (
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] mr-[10px]">
                            <span>{t('log.integration.winlogEventId')}</span>
                            <Tooltip
                              title={t(
                                `log.integration.${eventIdHintKey || 'winlogEventIdHint'}`
                              )}
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={[name, 'event_id']}
                          >
                            <Input
                              placeholder="4624, 4625, 4700-4800, -4735"
                              disabled={disabledFormItems[`${name}_event_id`]}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                    )}
                  </>
                )}
              </div>
            );
          }}
        </Form.Item>
      </>
    );
  };

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems?: Record<string, boolean>;
        hiddenFormItems?: Record<string, boolean>;
      } = {}
    ) => {
      const { disabledFormItems = {} } = extra;

      return (
        <>
          {/* Security Log Section */}
          {renderLogSection(
            'security',
            'winlogSecurityLog',
            'winlogSecurityLogDesc',
            true,
            disabledFormItems,
            true,
            'winlogSecurityEventIdHint'
          )}

          {/* System Log Section */}
          {renderLogSection(
            'system',
            'winlogSystemLog',
            'winlogSystemLogDesc',
            true,
            disabledFormItems
          )}

          {/* Application Log Section */}
          {renderLogSection(
            'application',
            'winlogApplicationLog',
            'winlogApplicationLogDesc',
            true,
            disabledFormItems
          )}

          {/* Sysmon Log Section */}
          {renderLogSection(
            'sysmon',
            'winlogSysmonLog',
            'winlogSysmonLogDesc',
            false,
            disabledFormItems
          )}

          {/* PowerShell Log Section */}
          {renderLogSection(
            'powershell',
            'winlogPowershellLog',
            'winlogPowershellLogDesc',
            false,
            disabledFormItems
          )}

          {/* Windows Defender Log Section */}
          {renderLogSection(
            'defender',
            'winlogDefenderLog',
            'winlogDefenderLogDesc',
            false,
            disabledFormItems
          )}

          {/* Task Scheduler Log Section */}
          {renderLogSection(
            'task_scheduler',
            'winlogTaskSchedulerLog',
            'winlogTaskSchedulerLogDesc',
            false,
            disabledFormItems
          )}

          {/* Ignore Older (Global Setting) */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.winlogIgnoreOlder')}
              </span>
              <Tooltip title={t('log.integration.winlogIgnoreOlderHint')}>
                <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
              </Tooltip>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.winlogIgnoreOlderDesc')}
          </div>
          <Form.Item className="mb-[20px]" name="ignore_older">
            <Input
              placeholder="72h"
              disabled={disabledFormItems.ignore_older}
            />
          </Form.Item>
        </>
      );
    }
  };
};

export { useWinlogbeatFormItems };
