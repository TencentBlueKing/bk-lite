'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Button,
  Form,
  Input,
  Radio,
  Select,
  DatePicker,
  TimePicker,
  InputNumber,
  Segmented,
  message,
  Spin,
  Alert,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { JobType, ScheduleType, ScheduledTaskFormData, Script, Playbook } from '@/app/job/types';
import { useRouter } from 'next/navigation';
import dayjs from 'dayjs';
import HostSelectionModal, { HostItem, TargetSourceType } from '@/app/job/components/host-selection-modal';
import { useUserInfoContext } from '@/context/userInfo';

const CreateCronTaskPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading: isApiReady } = useApiClient();
  const {
    createScheduledTask,
    getScriptList,
    getPlaybookList,
    getCrontabPreview,
  } = useJobApi();
  const { selectedGroup } = useUserInfoContext();

  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [jobType, setJobType] = useState<JobType>('script');
  const [templateType, setTemplateType] = useState<'script' | 'playbook'>('script');
  const [scheduleStrategy, setScheduleStrategy] = useState<'simple' | 'advanced'>('simple');
  const [simpleScheduleType, setSimpleScheduleType] = useState<'daily' | 'hourly' | 'once'>('daily');

  const [scripts, setScripts] = useState<Script[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);

  // Host selection state (matching HostSelectionModal interface)
  const [hostModalOpen, setHostModalOpen] = useState(false);
  const [targetSource, setTargetSource] = useState<TargetSourceType>('target_manager');
  const [selectedHostKeys, setSelectedHostKeys] = useState<string[]>([]);
  const [selectedHosts, setSelectedHosts] = useState<HostItem[]>([]);

  // Cron editor state
  const [cronMinute, setCronMinute] = useState('2');
  const [cronHour, setCronHour] = useState('*');
  const [cronDay, setCronDay] = useState('1');
  const [cronMonth, setCronMonth] = useState('*');
  const [cronWeek, setCronWeek] = useState('*');

  // Cron preview state
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchScripts = useCallback(async () => {
    try {
      const res = await getScriptList({ page_size: 100 });
      setScripts(res.items || []);
    } catch {
      // error handled
    }
  }, [getScriptList]);

  const fetchPlaybooks = useCallback(async () => {
    try {
      const res = await getPlaybookList({ page_size: 100 });
      setPlaybooks(res.items || []);
    } catch {
      // error handled
    }
  }, [getPlaybookList]);

  useEffect(() => {
    if (!isApiReady) {
      fetchScripts();
      fetchPlaybooks();
    }
  }, [isApiReady]);

  const getCronExpression = (): string => {
    return `${cronMinute} ${cronHour} ${cronDay} ${cronMonth} ${cronWeek}`;
  };

  const fetchCronPreview = useCallback(async (cronExpr: string) => {
    if (!cronExpr || cronExpr.split(' ').length !== 5) return;
    setPreviewLoading(true);
    try {
      const res = await getCrontabPreview(cronExpr);
      if (res.result && res.data?.next_runs) {
        setNextRuns(res.data.next_runs);
      }
    } catch {
      setNextRuns([]);
    } finally {
      setPreviewLoading(false);
    }
  }, [getCrontabPreview]);

  useEffect(() => {
    if (scheduleStrategy === 'advanced') {
      const cronExpr = getCronExpression();
      const timer = setTimeout(() => {
        fetchCronPreview(cronExpr);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [cronMinute, cronHour, cronDay, cronMonth, cronWeek, scheduleStrategy]);

  const describeCron = (): string => {
    if (cronMinute === '*' && cronHour === '*' && cronDay === '*' && cronMonth === '*' && cronWeek === '*') {
      return t('job.cronEveryMinute');
    }

    const parts: string[] = [];

    if (cronMonth !== '*') {
      parts.push(t('job.cronDescMonth').replace('{month}', cronMonth));
    }
    if (cronDay !== '*') {
      if (cronMonth === '*') {
        parts.push(t('job.cronDescEveryMonthDay').replace('{day}', cronDay));
      } else {
        parts.push(t('job.cronDescDay').replace('{day}', cronDay));
      }
    }
    if (cronWeek !== '*') {
      parts.push(t('job.cronDescWeek').replace('{week}', cronWeek));
    }
    if (cronHour !== '*') {
      if (cronHour.includes('/')) {
        parts.push(t('job.cronDescHourInterval').replace('{interval}', cronHour.replace('*/', '')));
      } else {
        parts.push(t('job.cronDescHour').replace('{hour}', cronHour));
      }
    } else if (cronDay !== '*' || cronWeek !== '*') {
      parts.push(t('job.cronDescEveryHour'));
    }
    if (cronMinute !== '*') {
      parts.push(t('job.cronDescMinute').replace('{minute}', cronMinute.padStart(2, '0')));
    }

    return parts.join(' ') || getCronExpression();
  };

  const getSimpleCronExpression = (): { cron_expression?: string; scheduled_time?: string; schedule_type: ScheduleType } => {
    const dailyTime = form.getFieldValue('dailyTime');
    const hourlyInterval = form.getFieldValue('hourlyInterval') || 1;
    const hourlyMinute = form.getFieldValue('hourlyMinute') || 0;
    const onceDateTime = form.getFieldValue('onceDateTime');

    switch (simpleScheduleType) {
      case 'daily': {
        const hour = dailyTime ? dailyTime.hour() : 2;
        const minute = dailyTime ? dailyTime.minute() : 0;
        return {
          cron_expression: `${minute} ${hour} * * *`,
          schedule_type: 'cron',
        };
      }
      case 'hourly':
        return {
          cron_expression: `${hourlyMinute} */${hourlyInterval} * * *`,
          schedule_type: 'cron',
        };
      case 'once':
      default:
        return {
          scheduled_time: onceDateTime ? onceDateTime.toISOString() : undefined,
          schedule_type: 'once',
        };
    }
  };

  const handleSubmit = async (enableAfterSave: boolean = false) => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      let scheduleData: { cron_expression?: string; scheduled_time?: string; schedule_type: ScheduleType };

      if (scheduleStrategy === 'simple') {
        scheduleData = getSimpleCronExpression();
      } else {
        scheduleData = {
          cron_expression: getCronExpression(),
          schedule_type: 'cron',
        };
      }

      // Convert to target_source + target_list format
      const targetList = selectedHosts.map((h) => ({
        ...(targetSource === 'node_manager'
          ? { node_id: h.key }
          : { target_id: Number(h.key) }),
        name: h.hostName,
        ip: h.ipAddress,
        os: h.osType?.toLowerCase() as 'linux' | 'windows',
      }));

      const formData: ScheduledTaskFormData = {
        name: values.name,
        description: values.description,
        job_type: jobType,
        ...scheduleData,
        target_source: targetSource === 'node_manager' ? 'node_mgmt' : 'manual',
        target_list: targetList,
        timeout: values.timeout || 60,
        is_enabled: enableAfterSave,
        team: selectedGroup ? [Number(selectedGroup.id)] : [],
      };

      if (jobType === 'script') {
        if (templateType === 'script') {
          formData.script = values.script;
        } else {
          formData.playbook = values.playbook;
        }
      } else if (jobType === 'file') {
        formData.target_path = values.target_path;
      }

      await createScheduledTask(formData);
      message.success(t('job.createTaskSuccess'));
      router.push('/job/execution/cron-task');
    } catch {
      // validation or API error
    } finally {
      setSubmitting(false);
    }
  };

  const handleHostConfirm = (keys: string[], hosts: HostItem[]) => {
    setSelectedHostKeys(keys);
    setSelectedHosts(hosts);
    setHostModalOpen(false);
  };

  const handleTargetSourceChange = (val: TargetSourceType) => {
    setTargetSource(val);
    setSelectedHostKeys([]);
    setSelectedHosts([]);
    if (val === 'node_manager' && templateType === 'playbook') {
      setTemplateType('script');
      form.setFieldValue('playbook', undefined);
    }
  };

  const handleTemplateTypeChange = (value: string | number) => {
    if (targetSource === 'node_manager' && value === 'playbook') {
      return;
    }
    setTemplateType(value as 'script' | 'playbook');
    if (value === 'script') {
      form.setFieldValue('playbook', undefined);
    } else {
      form.setFieldValue('script', undefined);
    }
  };

  return (
    <div className="w-full h-full overflow-auto pb-6">
      <div
        className="rounded-lg px-6 py-4 mb-4"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2 className="text-base font-medium m-0 mb-1" style={{ color: 'var(--color-text-1)' }}>
          {t('job.createTask')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.createTaskDesc')}
        </p>
      </div>

      <div
        className="rounded-lg px-6 py-6"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <Form
          form={form}
          layout="vertical"
          className="max-w-[720px]"
          initialValues={{
            timeout: 300,
            dailyTime: dayjs().hour(2).minute(0),
            hourlyInterval: 1,
            hourlyMinute: 0,
          }}
        >
          <Form.Item
            label={t('job.taskName')}
            name="name"
            rules={[{ required: true, message: t('job.taskNameRequired') }]}
          >
            <Input placeholder={t('job.taskNamePlaceholder')} />
          </Form.Item>

          <Form.Item label={t('job.description')} name="description">
            <Input.TextArea
              rows={2}
              placeholder={t('job.descriptionPlaceholder')}
            />
          </Form.Item>

          <Form.Item label={t('job.targetSource')} required>
            <Radio.Group
              value={targetSource}
              onChange={(e) => handleTargetSourceChange(e.target.value)}
            >
              <Radio value="node_manager">{t('job.nodeManager')}</Radio>
              <Radio value="target_manager">{t('job.targetManager')}</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item label={t('job.targetHost')} required>
            <div className="flex items-center gap-3">
              <Button type="dashed" onClick={() => setHostModalOpen(true)}>
                + {t('job.addTargetHost')}
              </Button>
              <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                {t('job.selectedHosts').replace('{count}', String(selectedHosts.length))}
              </span>
            </div>
          </Form.Item>

          <Form.Item label={t('job.jobType')} required>
            <Radio.Group
              value={jobType}
              onChange={(e) => setJobType(e.target.value)}
            >
              <Radio value="script">{t('job.scriptExecution')}</Radio>
              <Radio value="file">{t('job.fileDistribution')}</Radio>
            </Radio.Group>
          </Form.Item>

          {jobType === 'script' && (
            <Form.Item label={t('job.selectTemplate')} required>
              {targetSource === 'node_manager' && (
                <Alert
                  className="mb-2"
                  message={t('job.nodeManagerPlaybookNotSupported')}
                  type="warning"
                  showIcon
                />
              )}
              <Segmented
                className="w-fit mb-2"
                options={[
                  { label: t('job.scriptLibrary'), value: 'script' },
                  { label: 'Playbook', value: 'playbook', disabled: targetSource === 'node_manager' },
                ]}
                value={templateType}
                onChange={handleTemplateTypeChange}
              />
              {templateType === 'script' ? (
                <Form.Item
                  name="script"
                  noStyle
                  rules={[{ required: true, message: t('job.selectScriptRequired') }]}
                >
                  <Select placeholder={t('job.selectScript')}>
                    {scripts.map((script) => (
                      <Select.Option key={script.id} value={script.id}>
                        {script.name}
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
              ) : (
                <Form.Item
                  name="playbook"
                  noStyle
                  rules={[{ required: true, message: t('job.selectPlaybookRequired') }]}
                >
                  <Select placeholder={t('job.selectPlaybook')}>
                    {playbooks.map((playbook) => (
                      <Select.Option key={playbook.id} value={playbook.id}>
                        {playbook.name}
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
            </Form.Item>
          )}

          {jobType === 'file' && (
            <Form.Item
              label={t('job.fileDistTargetPath')}
              name="target_path"
              rules={[{ required: true, message: t('job.targetPathRequired') }]}
            >
              <Input placeholder={t('job.fileDistTargetPathPlaceholder')} />
            </Form.Item>
          )}

          <Form.Item label={t('job.scheduleStrategy')} required>
            <Segmented
              className="w-fit mb-4"
              options={[
                { label: t('job.simpleStrategy'), value: 'simple' },
                { label: t('job.advancedStrategy'), value: 'advanced' },
              ]}
              value={scheduleStrategy}
              onChange={(value) => setScheduleStrategy(value as 'simple' | 'advanced')}
            />

            {scheduleStrategy === 'simple' ? (
              <div className="space-y-3">
                <Radio.Group
                  value={simpleScheduleType}
                  onChange={(e) => setSimpleScheduleType(e.target.value)}
                  className="flex flex-col gap-3"
                >
                  <Radio value="daily" className="flex items-center">
                    <span className="mr-2">{t('job.dailyOnce')}</span>
                    <Form.Item name="dailyTime" noStyle>
                      <TimePicker
                        format="HH:mm"
                        disabled={simpleScheduleType !== 'daily'}
                        className="w-24"
                      />
                    </Form.Item>
                  </Radio>
                  <Radio value="hourly">
                    <span className="inline-flex items-center flex-nowrap whitespace-nowrap">
                      <span className="mr-2">{t('job.every')}</span>
                      <Form.Item name="hourlyInterval" noStyle>
                        <Select disabled={simpleScheduleType !== 'hourly'} className="w-20">
                          {[1, 2, 3, 4, 6, 8, 12].map((n) => (
                            <Select.Option key={n} value={n}>{n}</Select.Option>
                          ))}
                        </Select>
                      </Form.Item>
                      <span className="mx-2 whitespace-nowrap">{t('job.hoursAt')}</span>
                      <Form.Item name="hourlyMinute" noStyle>
                        <InputNumber min={0} max={59} disabled={simpleScheduleType !== 'hourly'} className="w-28" />
                      </Form.Item>
                      <span className="ml-2">{t('job.minute')}</span>
                    </span>
                  </Radio>
                  <Radio value="once" className="flex items-center">
                    <span className="mr-2">{t('job.executeOnceAt')}</span>
                    <Form.Item name="onceDateTime" noStyle>
                      <DatePicker
                        showTime
                        disabled={simpleScheduleType !== 'once'}
                        format="YYYY-MM-DD HH:mm"
                      />
                    </Form.Item>
                  </Radio>
                </Radio.Group>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex gap-2 text-xs text-[var(--color-text-3)] pl-1">
                  <span className="w-12 text-center">{t('job.cronMinute')}</span>
                  <span className="w-12 text-center">{t('job.cronHour')}</span>
                  <span className="w-12 text-center">{t('job.cronDay')}</span>
                  <span className="w-12 text-center">{t('job.cronMonth')}</span>
                  <span className="w-12 text-center">{t('job.cronWeek')}</span>
                </div>
                <div className="flex gap-2">
                  {[
                    { value: cronMinute, setter: setCronMinute },
                    { value: cronHour, setter: setCronHour },
                    { value: cronDay, setter: setCronDay },
                    { value: cronMonth, setter: setCronMonth },
                    { value: cronWeek, setter: setCronWeek },
                  ].map((field, index) => (
                    <Input
                      key={index}
                      value={field.value}
                      onChange={(e) => field.setter(e.target.value)}
                      onBlur={(e) => { if (!e.target.value.trim()) field.setter('*'); }}
                      className="w-12 text-center font-mono"
                      style={{ borderColor: 'var(--color-primary)' }}
                    />
                  ))}
                </div>
                <div className="text-sm text-[var(--color-text-2)] text-center" style={{ width: '296px' }}>
                  {describeCron()}
                </div>
                <div className="text-sm text-center" style={{ width: '296px' }}>
                  {previewLoading ? (
                    <>
                      <span className="text-[var(--color-text-3)] text-xs">{t('job.cronNextRun')}</span>
                      <Spin size="small" className="ml-2" />
                    </>
                  ) : nextRuns.length > 0 ? (
                    <>
                      <span className="text-[var(--color-text-3)] text-xs">{t('job.cronNextRun')}</span>
                      <div className="mt-1 max-h-[54px] overflow-y-auto space-y-0.5">
                        {nextRuns.map((time, idx) => (
                          <div key={idx} className="text-[var(--color-text-3)] font-mono text-xs">
                            {time}
                          </div>
                        ))}
                      </div>
                      {nextRuns.length > 3 && (
                        <div className="text-[var(--color-text-4)] text-xs mt-0.5">···</div>
                      )}
                    </>
                  ) : null}
                </div>
              </div>
            )}
          </Form.Item>

          <Form.Item label={t('job.concurrencyStrategy')} name="concurrency_strategy">
            <Select defaultValue="skip">
              <Select.Option value="skip">{t('job.skipIfRunning')}</Select.Option>
              <Select.Option value="run">{t('job.runAnyway')}</Select.Option>
              <Select.Option value="queue">{t('job.queueWait')}</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item label={t('job.timeout')} name="timeout">
            <InputNumber min={1} max={86400} className="w-full" addonAfter={t('job.seconds')} />
          </Form.Item>

          <Form.Item className="mb-0">
            <div className="flex gap-3 pt-4 border-t border-[var(--color-border)]">
              <Button type="primary" loading={submitting} onClick={() => handleSubmit(true)}>
                {t('job.saveAndEnable')}
              </Button>
              <Button loading={submitting} onClick={() => handleSubmit(false)}>
                {t('job.saveOnly')}
              </Button>
              <Button onClick={() => router.back()}>
                {t('job.cancel')}
              </Button>
            </div>
          </Form.Item>
        </Form>
      </div>

      <HostSelectionModal
        open={hostModalOpen}
        selectedKeys={selectedHostKeys}
        source={targetSource}
        onConfirm={handleHostConfirm}
        onCancel={() => setHostModalOpen(false)}
      />
    </div>
  );
};

export default CreateCronTaskPage;
