'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  ReactNode,
} from 'react';
import { Input, Button, Form, message, Select, Tooltip } from 'antd';
import Icon from '@/components/icon';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import useApiClient from '@/utils/request';
import {
  ModalRef,
  ListItem,
  GroupInfo,
  ObjectItem,
  MetricItem,
  IndexViewItem,
  FilterItem,
} from '@/app/monitor/types';
import { RuleInfo, GroupingRules } from '@/app/monitor/types/integration';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import GroupTreeSelector from '@/components/group-tree-select';
import useMonitorApi from '@/app/monitor/api';
import { useConditionList } from '@/app/monitor/hooks';
import strategyStyle from './index.module.scss';
import { cloneDeep } from 'lodash';
const { Option } = Select;

interface ModalProps {
  onSuccess: () => void;
  groupList: ListItem[];
  monitorObject: React.Key;
  objects: ObjectItem[];
}

const RuleModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, monitorObject, objects }, ref) => {
    const { post, put } = useApiClient();
    const { t } = useTranslation();
    const { getMetricsGroup, getMonitorMetrics } = useMonitorApi();
    const CONDITION_LIST = useConditionList();
    const formRef = useRef<FormInstance>(null);
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<RuleInfo>({});
    const [title, setTitle] = useState<ReactNode>('');
    const [type, setType] = useState<string>('');
    const [metricsLoading, setMetricsLoading] = useState<boolean>(false);
    const [originMetricData, setOriginMetricData] = useState<IndexViewItem[]>(
      []
    );
    const [metrics, setMetrics] = useState<MetricItem[]>([]);
    const [metric, setMetric] = useState<number | null>();
    const [labels, setLabels] = useState<string[]>([]);
    const [conditions, setConditions] = useState<FilterItem[]>([
      {
        name: null,
        method: null,
        value: '',
      },
    ]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form, title }) => {
        // 开启弹窗的交互
        const formData = cloneDeep(form);
        setGroupVisible(true);
        setType(type);
        const dom = (
          <Tooltip
            placement="top"
            title={t('monitor.integrations.ruleModalTips')}
          >
            <span className="w-[200] relative">
              {title}
              <Icon
                type="a-shuoming2"
                className="text-[14px] text-[var(--color-text-3)] absolute cursor-pointer"
                style={{
                  top: '-4px',
                  right: '-14px',
                }}
              />
            </span>
          </Tooltip>
        );
        setTitle(dom);
        if (type === 'edit' && formData.rule) {
          setConditions(formData.rule.filter);
          setMetric(formData.rule.metric_id);
        }
        setGroupForm(formData);
        getMetrics({ monitor_object_id: monitorObject });
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    useEffect(() => {
      if (originMetricData.length) {
        const metricId = groupForm?.rule?.metric_id;
        if (metricId) {
          handleMetricChange(metricId);
          formRef.current?.setFieldsValue({
            metric: metricId,
          });
        }
      }
    }, [originMetricData, groupForm]);

    const getMetrics = async (params = {}) => {
      try {
        setMetricsLoading(true);
        const getGroupList = getMetricsGroup(params);
        const getMetrics = getMonitorMetrics(params);
        Promise.all([getGroupList, getMetrics])
          .then((res) => {
            const metricData = cloneDeep(res[1] || []);
            setMetrics(res[1] || []);
            const groupData = res[0].map((item: GroupInfo) => ({
              ...item,
              child: [],
            }));
            metricData.forEach((metric: MetricItem) => {
              const target = groupData.find(
                (item: GroupInfo) => item.id === metric.metric_group
              );
              if (target) {
                target.child.push(metric);
              }
            });
            const _groupData = groupData.filter(
              (item: any) => !!item.child?.length
            );
            setOriginMetricData(_groupData);
          })
          .finally(() => {
            setMetricsLoading(false);
          });
      } catch {
        setMetricsLoading(false);
      }
    };

    const operateGroup = async (params: RuleInfo) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add'
            ? 'common.successfullyAdded'
            : 'common.successfullyModified'
        );
        const url: string =
          type === 'add'
            ? '/monitor/api/organization_rule/'
            : `/monitor/api/organization_rule/${groupForm.id}/`;
        const requestType = type === 'add' ? post : put;
        await requestType(url, params);
        message.success(msg);
        handleCancel();
        onSuccess();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const rule: GroupingRules = {
          type: 'metric',
          metric_id: metric as number,
          filter: conditions,
        };
        operateGroup({
          name: values.name,
          monitor_object: monitorObject as number,
          rule,
          organizations: values.organizations || [],
        });
      });
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setConditions([
        {
          name: null,
          method: null,
          value: '',
        },
      ]);
      setLabels([]);
      setOriginMetricData([]);
    };

    const handleMetricChange = (val: number) => {
      setMetric(val);
      const target = metrics.find((item) => item.id === val);
      const labelKeys = (target?.dimensions || []).map((item) => item.name);
      const instanceIdKeys =
        objects.find((item) => item.id === monitorObject)?.instance_id_keys ||
        [];
      const keys = [
        ...new Set([...labelKeys, ...(instanceIdKeys as string[])]),
      ];
      setLabels(keys);
    };

    const handleLabelChange = (val: string, index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].name = val;
      setConditions(_conditions);
    };

    const handleConditionChange = (val: string, index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].method = val;
      setConditions(_conditions);
    };

    const handleValueChange = (
      e: React.ChangeEvent<HTMLInputElement>,
      index: number
    ) => {
      const _conditions = cloneDeep(conditions);
      _conditions[index].value = e.target.value;
      setConditions(_conditions);
    };

    const addConditionItem = () => {
      const _conditions = cloneDeep(conditions);
      _conditions.push({
        name: null,
        method: null,
        value: '',
      });
      setConditions(_conditions);
    };

    const deleteConditionItem = (index: number) => {
      const _conditions = cloneDeep(conditions);
      _conditions.splice(index, 1);
      setConditions(_conditions);
    };

    // 自定义验证条件列表
    const validateDimensions = async () => {
      if (!conditions.length) {
        return Promise.reject(new Error(t('common.required')));
      }
      if (
        conditions.length &&
        conditions.some((item) => {
          return Object.values(item).some((tex) => !tex);
        })
      ) {
        return Promise.reject(new Error(t('monitor.events.conditionValidate')));
      }
      return Promise.resolve();
    };

    return (
      <div>
        <OperateModal
          width={600}
          title={title}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form
            ref={formRef}
            name="basic"
            labelCol={{ span: 4 }}
            wrapperCol={{ span: 18 }}
          >
            <Form.Item<RuleInfo>
              label={t('common.name')}
              name="name"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Input />
            </Form.Item>
            <Form.Item<RuleInfo>
              label={t('monitor.metric')}
              name="metric"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Select
                allowClear
                placeholder={t('monitor.metric')}
                showSearch
                value={metric}
                loading={metricsLoading}
                options={originMetricData.map((item) => ({
                  label: item.display_name,
                  title: item.name,
                  options: (item.child || []).map((tex) => ({
                    label: tex.display_name,
                    value: tex.id,
                  })),
                }))}
                onChange={handleMetricChange}
              />
            </Form.Item>
            <Form.Item<RuleInfo>
              label={t('monitor.integrations.condition')}
              name="rule"
              rules={[{ required: true, validator: validateDimensions }]}
            >
              <div className={strategyStyle.conditionItem}>
                {conditions.length ? (
                  <ul className={strategyStyle.conditions}>
                    {conditions.map((conditionItem, index) => (
                      <li
                        className={`${strategyStyle.itemOption} ${strategyStyle.filter}`}
                        key={index}
                      >
                        <Select
                          style={{
                            width: '150px',
                          }}
                          placeholder={t('monitor.label')}
                          showSearch
                          value={conditionItem.name}
                          onChange={(val) => handleLabelChange(val, index)}
                        >
                          {labels.map((item: string) => (
                            <Option value={item} key={item}>
                              {item}
                            </Option>
                          ))}
                        </Select>
                        <Select
                          style={{
                            width: '90px',
                          }}
                          placeholder={t('monitor.term')}
                          value={conditionItem.method}
                          onChange={(val) => handleConditionChange(val, index)}
                        >
                          {CONDITION_LIST.map((item: ListItem) => (
                            <Option value={item.id} key={item.id}>
                              {item.name}
                            </Option>
                          ))}
                        </Select>
                        <Input
                          style={{
                            width: '100px',
                          }}
                          placeholder={t('monitor.value')}
                          value={conditionItem.value}
                          onChange={(e) => handleValueChange(e, index)}
                        ></Input>
                        {!!index && (
                          <Button
                            icon={<CloseOutlined />}
                            onClick={() => deleteConditionItem(index)}
                          />
                        )}
                        <Button
                          icon={<PlusOutlined />}
                          onClick={addConditionItem}
                        />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Button
                    disabled={!metric}
                    icon={<PlusOutlined />}
                    onClick={addConditionItem}
                  />
                )}
              </div>
            </Form.Item>
            <Form.Item<RuleInfo>
              label={t('monitor.group')}
              name="organizations"
              rules={[{ required: true, message: t('common.required') }]}
            >
              <GroupTreeSelector placeholder={t('common.selectMsg')} />
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
RuleModal.displayName = 'RuleModal';
export default RuleModal;
