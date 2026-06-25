'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Button,
  Checkbox,
  Drawer,
  Form,
  Input,
  Select,
  Switch,
  Tooltip,
  message,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';
import GroupTreeSelect from '@/components/group-tree-select';
import FieldBindingTable, { ScriptParam } from './fieldBindingTable';
import { ActionConfig, ActionRuleListItem } from '@/app/alarm/types/settings';
import {
  ACTION_TRIGGER_EVENTS,
  ACTION_TYPES,
} from '@/app/alarm/constants/settings';

interface OperateModalProps {
  open: boolean;
  currentRow?: ActionRuleListItem | null;
  onClose: () => void;
  onSuccess?: () => void;
}

interface JobScript {
  id: number;
  name: string;
  params?: ScriptParam[];
}

const DEFAULT_MATCH_RULES: ActionRuleListItem['match_rules'] = [
  [{ key: 'resource_type', operator: 'eq', value: '' }],
];

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const locale =
    typeof window !== 'undefined'
      ? localStorage.getItem('locale') || 'en'
      : 'en';
  const { t } = useTranslation();
  const {
    createActionRule,
    updateActionRule,
    getActionJobScripts,
    getActionJobScript,
  } = useSettingApi();

  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);
  const [scriptOptions, setScriptOptions] = useState<
    { value: number; label: string }[]
  >([]);
  const [scriptParams, setScriptParams] = useState<ScriptParam[]>([]);
  const [scriptLoading, setScriptLoading] = useState(false);
  const [scriptDetailLoading, setScriptDetailLoading] = useState(false);

  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchScripts = useCallback(
    async (name?: string) => {
      setScriptLoading(true);
      try {
        // request.ts 已 unwrap 到 data；job_mgmt 列表分页返回 { items, count }
        const res = (await getActionJobScripts({ name })) as unknown;
        const list: JobScript[] = Array.isArray(res)
          ? (res as JobScript[])
          : ((res as { items?: JobScript[]; data?: JobScript[] })?.items ||
             (res as { items?: JobScript[]; data?: JobScript[] })?.data ||
             []);
        setScriptOptions(list.map((s) => ({ value: s.id, label: s.name })));
      } catch {
        // ignore
      } finally {
        setScriptLoading(false);
      }
    },
    [getActionJobScripts]
  );

  const fetchScriptDetail = useCallback(
    async (id: number) => {
      setScriptDetailLoading(true);
      try {
        const data = (await getActionJobScript(id)) as JobScript;
        setScriptParams(data?.params || []);
        return data?.params || [];
      } catch {
        setScriptParams([]);
        return [];
      } finally {
        setScriptDetailLoading(false);
      }
    },
    [getActionJobScript]
  );

  const handleClose = () => {
    form.resetFields();
    setScriptParams([]);
    setScriptOptions([]);
    onClose();
  };

  useEffect(() => {
    if (!open) return;

    fetchScripts();

    if (currentRow) {
      const config = currentRow.action_config || ({} as ActionConfig);
      form.setFieldsValue({
        name: currentRow.name,
        team: currentRow.team || [],
        is_active: currentRow.is_active,
        trigger_events: currentRow.trigger_events || [],
        match_rules:
          currentRow.match_rules?.length
            ? currentRow.match_rules
            : DEFAULT_MATCH_RULES,
        action_type: currentRow.action_type || 'job',
        script_id: config.script_id,
        host_field: config.target_binding?.host_field || 'ip_addr',
        param_bindings: config.param_bindings || [],
      });

      if (config.script_id) {
        fetchScriptDetail(config.script_id).then((params) => {
          form.setFieldsValue({ param_bindings: config.param_bindings || [] });
          setScriptParams(params);
        });
      }
    } else {
      form.resetFields();
      form.setFieldsValue({
        is_active: true,
        action_type: 'job',
        host_field: 'ip_addr',
        param_bindings: [],
        match_rules: DEFAULT_MATCH_RULES,
        trigger_events: [],
      });
      setScriptParams([]);
    }
  }, [open, currentRow]);

  const handleScriptSearch = (name: string) => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      fetchScripts(name || undefined);
    }, 300);
  };

  const handleScriptChange = async (id: number) => {
    form.setFieldValue('param_bindings', []);
    await fetchScriptDetail(id);
  };

  const onFinish = async (values: Record<string, unknown>) => {
    setSubmitLoading(true);
    try {
      const scriptId = values.script_id as number | undefined;
      const hostField = (values.host_field as string) || 'ip_addr';
      const paramBindings = (values.param_bindings as ActionConfig['param_bindings']) || [];

      const actionConfig: ActionConfig = {
        script_id: scriptId,
        target_binding: {
          source: 'node_mgmt',
          match_by: 'ip',
          host_field: hostField,
        },
        param_bindings: paramBindings,
      };

      const payload = {
        name: values.name as string,
        team: (values.team as number[]) || [],
        is_active: values.is_active as boolean,
        trigger_events: (values.trigger_events as string[]) || [],
        match_rules: (values.match_rules as ActionRuleListItem['match_rules']) || [],
        action_type: (values.action_type as ActionRuleListItem['action_type']) || 'job',
        action_config: actionConfig,
      };

      if (currentRow?.id) {
        await updateActionRule(currentRow.id, payload);
      } else {
        await createActionRule(payload);
      }

      message.success(
        currentRow ? t('alarmCommon.successOperate') : t('common.addSuccess')
      );
      handleClose();
      onSuccess?.();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  const SectionTitle: React.FC<{ title: string }> = ({ title }) => (
    <div className="mb-3 mt-5 flex items-center">
      <div className="mr-2 h-[16px] w-[3px] rounded-sm bg-blue-500" />
      <span className="text-[15px] font-medium text-gray-700">{title}</span>
    </div>
  );

  return (
    <Drawer
      title={
        currentRow
          ? `${t('common.edit')} - ${currentRow.name}`
          : t('common.addNew')
      }
      placement="right"
      width={740}
      open={open}
      onClose={handleClose}
      maskClosable={false}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={submitLoading}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ span: locale === 'en' ? 6 : 5 }}
        wrapperCol={{ span: locale === 'en' ? 18 : 19 }}
        onFinish={onFinish}
      >
        {/* ① 基本信息 */}
        <SectionTitle title={t('settings.correlation.basicConfig')} />

        <Form.Item
          name="name"
          label={t('settings.actionRuleName')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Input placeholder={t('common.inputTip')} />
        </Form.Item>

        <Form.Item
          name="team"
          label={t('settings.correlation.organization')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <GroupTreeSelect multiple placeholder={t('common.selectTip')} />
        </Form.Item>

        {/* ② 触发时机 */}
        <SectionTitle title={t('settings.actionTriggerEvent')} />

        <Form.Item
          name="trigger_events"
          label=" "
          colon={false}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Checkbox.Group
            options={ACTION_TRIGGER_EVENTS.map(({ value, label }) => ({
              value,
              label,
            }))}
          />
        </Form.Item>

        <div className="mb-4 text-sm text-gray-500">
          {t('settings.actionTriggerTip')}
        </div>

        {/* ③ 匹配条件 */}
        <SectionTitle title={t('settings.assignStrategy.formMatchingRules')} />

        <Form.Item
          name="match_rules"
          validateTrigger={[]}
          style={{ marginBottom: '16px' }}
          rules={[
            {
              validator: (_: unknown, value: ActionRuleListItem['match_rules']) => {
                if (!Array.isArray(value) || value.length === 0) {
                  return Promise.resolve();
                }
                for (const orGroup of value) {
                  if (!Array.isArray(orGroup)) continue;
                  for (const item of orGroup) {
                    if (item.key && item.operator && (!item.value && item.value !== '0')) {
                      return Promise.reject(new Error(t('common.inputTip')));
                    }
                  }
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <MatchRule levelType="alert" />
        </Form.Item>

        <Form.Item
          name="is_active"
          label={t('settings.assignStartStop')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>

        {/* ④ 动作配置 */}
        <SectionTitle title={t('settings.actionType')} />

        <Form.Item
          name="action_type"
          label={t('settings.actionType')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select
            options={ACTION_TYPES.map(({ value, label, disabled }) => ({
              value,
              label: disabled ? (
                <Tooltip title="即将支持">
                  <span>{label}</span>
                </Tooltip>
              ) : (
                label
              ),
              disabled,
            }))}
          />
        </Form.Item>

        <Form.Item
          name="host_field"
          label={t('settings.actionTargetHostField')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Input placeholder="ip_addr" />
        </Form.Item>

        <Form.Item
          name="script_id"
          label={t('settings.actionSelectJob')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select
            showSearch
            loading={scriptLoading}
            filterOption={false}
            options={scriptOptions}
            placeholder={t('common.selectTip')}
            onSearch={handleScriptSearch}
            onChange={handleScriptChange}
          />
        </Form.Item>
        {scriptDetailLoading && (
          <div className="text-sm text-gray-400 mt-1 ml-4">{t('common.loading') || 'Loading...'}</div>
        )}

        {/* 仅当所选作业有脚本参数时才展示字段绑定 */}
        {scriptParams.length > 0 && (
          <Form.Item
            name="param_bindings"
            label={t('settings.actionFieldBinding')}
            style={{ marginBottom: 0 }}
          >
            <FieldBindingTable scriptParams={scriptParams} />
          </Form.Item>
        )}
      </Form>
    </Drawer>
  );
};

export default OperateModal;
