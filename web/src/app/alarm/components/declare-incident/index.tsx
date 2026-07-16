'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Radio, Select, message } from 'antd';
import OperateFormModal from '@/components/operate-form-modal';
import PermissionWrapper from '@/components/permission';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';

export interface DeclareIncidentRowData {
  id?: number | string;
  has_incident?: boolean;
  [key: string]: unknown;
}

export interface DeclareIncidentOption {
  label: string;
  value: string;
}

export interface DeclareIncidentLevelOption {
  label: string;
  value: string;
}

export interface DeclareIncidentSummary {
  id: number;
  title: string;
  alert?: number[];
  [key: string]: unknown;
}

export interface DeclareIncidentProps {
  rowData: DeclareIncidentRowData[];
  onSuccess: (result: any) => void;
  fetchIncidentList: (params: any) => Promise<DeclareIncidentSummary[]>;
  createIncident: (params: any) => Promise<any>;
  updateIncident: (
    id: string,
    params: any
  ) => Promise<any>;
  assigneeOptions: DeclareIncidentOption[];
  levelOptions: DeclareIncidentLevelOption[];
  initialTeamIds: number[];
  currentUsername: string;
}

const DeclareIncident: React.FC<DeclareIncidentProps> = ({
  rowData,
  onSuccess,
  fetchIncidentList,
  createIncident,
  updateIncident,
  assigneeOptions,
  levelOptions,
  initialTeamIds,
  currentUsername,
}) => {
  const { t } = useTranslation();

  const [form] = Form.useForm();
  const [visible, setVisible] = useState(false);
  const [mode, setMode] = useState<'create' | 'link'>('create');
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [incidentLoading, setIncidentLoading] = useState(false);
  const [incidentOptions, setIncidentOptions] = useState<DeclareIncidentSummary[]>(
    []
  );

  useEffect(() => {
    if (visible) {
      setIncidentLoading(true);
      fetchIncidentList({ page: -1 })
        .then((res) => {
          setIncidentOptions(res || []);
        })
        .finally(() => {
          setIncidentLoading(false);
        });
    } else {
      setIncidentOptions([]);
    }
  }, [visible, fetchIncidentList]);

  const onFinish = async (values: any) => {
    setConfirmLoading(true);
    try {
      const alertIds = rowData
        .map((row) => row.id)
        .filter((id): id is string | number => id !== undefined && id !== null);

      if (mode === 'create') {
        await createIncident({
          alert: alertIds,
          title: values.title,
          level: values.level,
          operator: values.assignee,
          team: (values.team || []).map(String),
        });
        message.success(
          t('alarms.createAndLinkIncident') + t('alarmCommon.success')
        );
      } else {
        const target = incidentOptions.find(
          (inc) => inc.id === values.incidentId
        );
        const existingAlerts: number[] = target?.alert || [];
        const selectedAlerts = alertIds;
        const alert_ids = Array.from(
          new Set([...existingAlerts, ...selectedAlerts])
        );
        await updateIncident(String(values.incidentId), {
          alert: alert_ids,
        });
        message.success(t('alarms.linkIncident') + t('alarmCommon.success'));
        rowData.forEach((r) => {
          r.has_incident = true;
        });
      }
      onSuccess({ mode, ...values });
      form.resetFields();
      setVisible(false);
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setConfirmLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setMode('create');
    setVisible(false);
  };

  return (
    <>
      <PermissionWrapper requiredPermissions={['Edit']}>
        <Button
          color="danger"
          type="dashed"
          variant="solid"
          disabled={rowData.length === 0}
          onClick={() => setVisible(true)}
        >
          {t('alarms.linkIncident')}
        </Button>
      </PermissionWrapper>
      <OperateFormModal
        open={visible}
        title={t('alarms.linkIncident')}
        confirmLoading={confirmLoading}
        onConfirm={() => form.submit()}
        confirmText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={handleCancel}
      >
        <Form
          form={form}
          layout="horizontal"
          onFinish={onFinish}
          initialValues={{
            mode: 'create',
            assignee: currentUsername ? [currentUsername] : [],
            team: initialTeamIds,
          }}
        >
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="mb-6 pl-6"
          >
            <Radio value="create">{t('alarms.createIncident')}</Radio>
            <Radio value="link">{t('alarms.linkIncident')}</Radio>
          </Radio.Group>

          {mode === 'create' ? (
            <>
              <Form.Item
                name="title"
                label={t('alarms.title')}
                labelCol={{ span: 4 }}
                wrapperCol={{ span: 20 }}
                rules={[{ required: true, message: t('common.inputTip') }]}
              >
                <Input placeholder={t('common.inputTip')} />
              </Form.Item>

              <Form.Item
                name="level"
                label={t('alarms.level')}
                labelCol={{ span: 4 }}
                wrapperCol={{ span: 20 }}
                rules={[{ required: true, message: t('common.selectTip') }]}
              >
                <Radio.Group>
                  {levelOptions.map((item) => (
                    <Radio key={item.value} value={item.value}>
                      {item.label}
                    </Radio>
                  ))}
                </Radio.Group>
              </Form.Item>

              <Form.Item
                name="assignee"
                label={t('alarms.assignee')}
                labelCol={{ span: 4 }}
                wrapperCol={{ span: 20 }}
                rules={[{ required: true, message: t('common.selectTip') }]}
              >
                <Select
                  mode="multiple"
                  allowClear
                  showSearch
                  maxTagCount={4}
                  placeholder={t('common.selectTip')}
                  options={assigneeOptions}
                  filterOption={(input, option) =>
                    (option?.label as string)
                      ?.toLowerCase()
                      .includes(input.toLowerCase())
                  }
                />
              </Form.Item>

              <Form.Item
                name="team"
                label={t('incidents.team')}
                labelCol={{ span: 4 }}
                wrapperCol={{ span: 20 }}
                rules={[{ required: true, message: t('incidents.teamRequired') }]}
              >
                <GroupTreeSelect
                  placeholder={t('incidents.selectTeam')}
                  multiple={true}
                  mode="ownership"
                />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="incidentId"
              label={t('alarms.incident')}
              labelCol={{ span: 4 }}
              wrapperCol={{ span: 20 }}
              rules={[{ required: true, message: t('common.selectTip') }]}
            >
              <Select
                allowClear
                showSearch
                placeholder={t('common.selectTip')}
                loading={incidentLoading}
                optionLabelProp="label"
              >
                {incidentOptions.map((inc) => (
                  <Select.Option
                    key={inc.id}
                    value={inc.id}
                    label={`${inc.title}`}
                  >
                    <div className="font-medium">{inc.title}</div>
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}
        </Form>
      </OperateFormModal>
    </>
  );
};

export default DeclareIncident;
