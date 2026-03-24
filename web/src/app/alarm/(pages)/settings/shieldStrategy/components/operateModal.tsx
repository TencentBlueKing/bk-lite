'use client';

import React, { useEffect, useState } from 'react';
import MatchRule from '@/app/alarm/(pages)/settings/components/matchRule';
import EffectiveTime, {
  defaultEffectiveTime,
} from '@/app/alarm/(pages)/settings/components/effectiveTime';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Form, Input, Radio, Button, Drawer, message } from 'antd';

interface OperateModalProps {
  open: boolean;
  currentRow?: any;
  onClose: () => void;
  onSuccess?: () => void;
}

const OperateModalPage: React.FC<OperateModalProps> = ({
  open,
  currentRow,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { createShield, updateShield } = useSettingApi();
  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  useEffect(() => {
    if (open) {
      if (currentRow) {
        form.setFieldsValue({
          name: currentRow.name,
          match_type: currentRow.match_type,
          match_rules: currentRow.match_rules,
          suppression_time: currentRow.suppression_time,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          match_type: 'all',
          suppression_time: defaultEffectiveTime,
        });
      }
    }
  }, [open, currentRow, form]);

  const ruleType = Form.useWatch('match_type', form);

  const onFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const params: any = {
        name: values.name,
        match_type: values.match_type,
        suppression_time: values.suppression_time,
      };
      if (values.match_type === 'filter') {
        params.match_rules = values.match_rules;
      }
      if (currentRow?.id) {
        await updateShield(currentRow.id, params);
      } else {
        await createShield(params);
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

  return (
    <Drawer
      title={
        currentRow
          ? t('settings.assignStrategy.editTitle') + ` - ${currentRow.name}`
          : t('settings.assignStrategy.addTitle')
      }
      placement="right"
      width={720}
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
            {t('settings.assignStrategy.submit')}
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
        labelCol={{ span: 4 }}
        onFinish={onFinish}
      >
        <Form.Item
          name="name"
          label={t('settings.assignName')}
          rules={[
            {
              required: true,
              message: t('common.inputTip'),
            },
          ]}
        >
          <Input placeholder={t('common.inputTip')} />
        </Form.Item>
        <Form.Item
          initialValue="all"
          name="match_type"
          label={t('settings.assignStrategy.formMatchingRules')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Radio.Group className="mt-1">
            <Radio value="all">{t('settings.assignStrategy.ruleAll')}</Radio>
            <Radio value="filter">
              {t('settings.assignStrategy.ruleFilter')}
            </Radio>
          </Radio.Group>
        </Form.Item>

        {ruleType === 'filter' && (
          <Form.Item
            name="match_rules"
            validateTrigger={[]}
            style={{
              marginLeft: '110px',
              marginTop: '-10px',
              marginBottom: '26px',
            }}
            rules={[
              {
                validator: (_, value: any[][]) => {
                  if (!Array.isArray(value) || value.length === 0) {
                    return Promise.reject(new Error(t('common.inputTip')));
                  }
                  for (const orGroup of value) {
                    if (!Array.isArray(orGroup) || orGroup.length === 0) {
                      return Promise.reject(new Error(t('common.inputTip')));
                    }
                    for (const item of orGroup) {
                      if (
                        !item.key ||
                        !item.operator ||
                        (!item.value && item.value !== 0)
                      ) {
                        return Promise.reject(new Error(t('common.inputTip')));
                      }
                    }
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <MatchRule />
          </Form.Item>
        )}

        <Form.Item
          name="suppression_time"
          label={t('settings.assignStrategy.effectiveTime')}
          initialValue={defaultEffectiveTime}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <EffectiveTime open={open} />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default OperateModalPage;
