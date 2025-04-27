'use client';

import React, { useRef, useState, useEffect } from 'react';
import { Form, Input, Select, Button, Space, Row, Col, message } from 'antd';
import { MinusCircleFilled, PlusOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { KnowledgeBase, KnowledgeBaseRagSource } from '@/app/opspilot/types/skill';
import styles from './index.module.scss';
import OperateModal from '@/components/operate-modal';
import KnowledgeBaseSelector from '@/app/opspilot/components/skill/knowledgeBaseSelector';
import { useSkillApi } from '@/app/opspilot/api/skill';

const { Option } = Select;

interface ModifyRuleModalProps {
  visible: boolean;
  onCancel: () => void;
  onOk: () => void;
  initialValues?: any;
}

const ModifyRuleModal: React.FC<ModifyRuleModalProps> = ({ visible, onCancel, onOk, initialValues }) => {
  const { t } = useTranslation();
  const { fetchSkillDetail, fetchKnowledgeBases, createRule, updateRule } = useSkillApi(); // Use useSkillApi to access methods
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const addButtonRef = useRef<{ add: () => void }>({ add: () => {} });
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [ragSources, setRagSources] = useState<KnowledgeBaseRagSource[]>([]);
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<number[]>([]);
  const [conditionsCount, setConditionsCount] = useState(1);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const { knowledge_base: knowledgeBase } = await fetchSkillDetail(id);
        const data = await fetchKnowledgeBases();
        setKnowledgeBases(data.filter((item: KnowledgeBase) => knowledgeBase.includes(item.id)));
      } catch (error) {
        console.error(t('common.fetchFailed'), error);
      } finally {
        setLoading(false);
      }
    };

    if (id) fetchData();
  }, [id]);

  useEffect(() => {
    if (initialValues) {
      form.setFieldsValue({
        ...initialValues,
        skill_prompt: initialValues.action_set?.skill_prompt
      });
      const { conditions, action_set: actionSet } = initialValues;
      setConditionsCount(conditions?.length || 1);
      const selectedKnowledgeBaseIds = actionSet?.knowledge_base_list || [];
      setSelectedKnowledgeBases(selectedKnowledgeBaseIds);
      const selectedRagSources = knowledgeBases.filter(source => selectedKnowledgeBaseIds.includes(source.id)).map(source => ({
        id: source.id,
        name: source.name,
        introduction: source.introduction || '',
      })) as KnowledgeBaseRagSource[];
      setRagSources(selectedRagSources);
    } else {
      form.resetFields();
      setRagSources([]);
      setSelectedKnowledgeBases([]);
      setConditionsCount(1);
    }
  }, [visible, initialValues, form]);

  const handleAddCondition = async () => {
    try {
      const values = await form.validateFields(['conditions']);
      addButtonRef.current.add();
      setConditionsCount(values.conditions.length + 1);
    } catch {
      message.error(t('common.inputRequired'));
    }
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setConfirmLoading(true);

      const postData = {
        skill: id,
        name: values.name,
        description: values.description,
        condition: {
          operator: values.conditionsOperator || 'or',
          conditions: values.conditions.map((cond: any) => ({
            type: cond.type,
            obj: cond.obj,
            value: cond.value,
          })),
        },
        action: values.action,
        action_set: {
          skill_prompt: values.skill_prompt,
          knowledge_base_list: selectedKnowledgeBases,
        },
      };

      if (initialValues?.key) {
        await updateRule(initialValues.key, postData);
      } else {
        await createRule(postData);
      }

      onOk();
    } catch (error) {
      console.error(error);
      message.error(t('common.inputRequired'));
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <OperateModal
      title={initialValues ? t('skill.rules.edit') : t('skill.rules.add')}
      visible={visible}
      onCancel={() => {
        onCancel();
      }}
      onOk={handleOk}
      loading={loading}
      confirmLoading={confirmLoading}
      width={900}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          conditionsOperator: 'or',
          conditions: [{ obj: 'user', type: 'ding_talk', operator: 'include', value: '' }],
          action: 0
        }}
      >
        <Form.Item
          name="name"
          label={t('skill.rules.name')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="description"
          label={t('skill.rules.description')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>

        <Form.Item label={t('skill.rules.condition')} required>
          <section className={`p-4 rounded-md ${styles.ruleContainer}`}>
            <Row gutter={16} className={`flex items-center ${styles.conditionOperatorColumn}`}>
              <Col span={4} className="relative flex flex-col items-center">
                <Form.Item
                  name="conditionsOperator"
                  className="my-auto z-10 w-full"
                >
                  {conditionsCount > 0 && (
                    <Select style={{ width: '80px' }}>
                      <Option value="or">OR</Option>
                      <Option value="and">AND</Option>
                    </Select>
                  )}
                </Form.Item>
              </Col>
              <Col span={20} className='relative'>
                <Form.List name="conditions">
                  {(fields, { add, remove }) => {
                    addButtonRef.current.add = () => {
                      add({ obj: 'user', type: 'ding_talk', operator: 'include', value: '' });
                      setConditionsCount(fields.length + 1);
                    };
                    return (
                      <>
                        {fields.map(({ key, name, ...restField }) => (
                          <Space
                            key={key}
                            align="baseline"
                            className={`flex items-center relative ${styles.conditionRow}`}
                          >
                            <Form.Item
                              {...restField}
                              name={[name, 'obj']}
                              rules={[{ required: true, message: t('common.inputRequired') }]}
                            >
                              <Select style={{ width: '100px' }} defaultValue="user" placeholder={`${t('skill.rules.questioner')}`}>
                                <Option value="user">User</Option>
                              </Select>
                            </Form.Item>
                            <Form.Item
                              {...restField}
                              name={[name, 'type']}
                              rules={[{ required: true, message: t('common.inputRequired') }]}
                            >
                              <Select style={{ width: '150px' }} defaultValue="ding_talk" placeholder={`${t('common.inputMsg')}${t('skill.rules.type')}`}>
                                <Option value="ding_talk">Ding Talk</Option>
                                <Option value="enterprise_wechat">Enterprise Wechat</Option>
                              </Select>
                            </Form.Item>
                            <Form.Item
                              {...restField}
                              name={[name, 'operator']}
                            >
                              <Select style={{ width: '100px' }} defaultValue="include" placeholder={`${t('common.inputMsg')}${t('skill.rules.operator')}`}>
                                <Option value="include">Include</Option>
                              </Select>
                            </Form.Item>
                            <Form.Item
                              {...restField}
                              name={[name, 'value']}
                              rules={[{ required: true, message: t('common.inputRequired') }]}
                            >
                              <Input className="w-30" placeholder={`${t('common.inputMsg')}${t('skill.rules.value')}`} />
                            </Form.Item>
                            <MinusCircleFilled
                              className="text-gray-400"
                              onClick={() => {
                                remove(name);
                                setConditionsCount(fields.length - 1);
                              }}
                            />
                          </Space>
                        ))}
                      </>
                    );
                  }}
                </Form.List>
              </Col>
            </Row>
            <Button
              type="dashed"
              className="mt-2"
              onClick={handleAddCondition}
              block
              icon={<PlusOutlined />}
            >
              {t('skill.rules.addCondition')}
            </Button>
          </section>
        </Form.Item>
        <Form.Item
          name="action"
          label={t('skill.rules.action')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Select rootClassName='mb-5' placeholder={t('skill.rules.action')} className="w-full" defaultValue={0}>
            <Option value={0}>Use defined knowledge and prompt</Option>
          </Select>
          <div className={`p-4 rounded-md ${styles.ruleContainer}`}>
            <Form.Item
              name="skill_prompt"
              label={t('skill.rules.prompt')}
            >
              <Input.TextArea />
            </Form.Item>
            <Form.Item
              label={t('skill.rules.knowledgeBase')}
            >
              <KnowledgeBaseSelector
                showScore={false}
                ragSources={ragSources}
                setRagSources={setRagSources}
                knowledgeBases={knowledgeBases}
                selectedKnowledgeBases={selectedKnowledgeBases}
                setSelectedKnowledgeBases={setSelectedKnowledgeBases}
              />
            </Form.Item>
          </div>
        </Form.Item>
      </Form >
    </OperateModal>
  );
};

export default ModifyRuleModal;
