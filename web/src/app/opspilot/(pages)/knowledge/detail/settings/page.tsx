'use client';

import React, { useEffect, useState } from 'react';
import { Form, Input, Button, Row, Col, message, Select, Spin } from 'antd';
import ConfigComponent from '@/app/opspilot/components/knowledge/config';
import { useTranslation } from '@/utils/i18n';
import useGroups from '@/app/opspilot/hooks/useGroups';
import { useSearchParams, useRouter } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import useFetchConfigData from '@/app/opspilot/hooks/useFetchConfigData';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { Option } = Select;

const SettingsPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const [form] = Form.useForm();
  const { groups, loading: groupsLoading } = useGroups();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const { formData, configData, setFormData, setConfigData, loading } = useFetchConfigData(id);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const { updateKnowledgeSettings } = useKnowledgeApi();

  useEffect(() => {
    if (!groupsLoading && groups.length > 0) {
      form.setFieldsValue({ team: [groups[0].id] });
    }
    form.setFieldsValue(formData);
  }, [groupsLoading, groups, form, formData]);

  const handleConfirm = () => {
    form.validateFields()
      .then(async values => {
        setConfirmLoading(true);
        const params = {
          name: values.name,
          introduction: values.introduction,
          team: values.team,
          embed_model: configData.selectedEmbedModel,
          enable_rerank: configData.rerankModel,
          rerank_model: configData.selectedRerankModel,
          enable_text_search: configData.selectedSearchTypes.includes('textSearch'),
          text_search_weight: configData.textSearchWeight,
          text_search_mode: configData.textSearchMode,
          enable_vector_search: configData.selectedSearchTypes.includes('vectorSearch'),
          vector_search_weight: configData.vectorSearchWeight,
          rag_k: configData.quantity,
          rag_num_candidates: configData.candidate,
          result_count: configData.resultCount,
          rerank_top_k: configData.rerankTopK,
        };

        try {
          await updateKnowledgeSettings(id, params);
          message.success(t('common.updateSuccess'));
        } catch (error) {
          message.error(t('common.updateFailed'));
          console.error(error);
        } finally {
          setConfirmLoading(false);
        }
      })
      .catch(errorInfo => {
        console.log(`${t('common.valFailed')}: ${errorInfo}`);
      });
  };

  const handleCancel = () => {
    router.back();
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '20px', position: 'relative' }}>
      <Spin spinning={groupsLoading || loading}>
        <Form
          form={form}
          layout="horizontal"
          name="my_form"
          labelCol={{ flex: '0 0 128px' }}
          wrapperCol={{ flex: '1' }}
          initialValues={formData}
          onValuesChange={(changedValues, allValues) => setFormData(allValues)}
        >
          <Form.Item
            name="name"
            label={t('knowledge.form.name')}
            rules={[{ required: true, message: `${t('common.inputMsg')}${t('knowledge.form.name')}!` }]}
          >
            <Input placeholder={t('common.input')} />
          </Form.Item>
          <Form.Item
            name="team"
            label={t('knowledge.form.group')}
            rules={[{ required: true, message: `${t('common.selectMsg')}${t('knowledge.form.introduction')}!` }]}
          >
            <Select mode="multiple" placeholder={t('common.select')}>
              {groups.map(group => (
                <Option key={group.id} value={group.id}>{group.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="introduction"
            label={t('knowledge.form.introduction')}
            rules={[{ required: true, message: `${t('common.inputMsg')}${t('knowledge.form.introduction')}!` }]}
          >
            <Input.TextArea rows={4} placeholder={t('common.input')} />
          </Form.Item>

          <ConfigComponent
            configData={configData}
            setConfigData={setConfigData}
          />

          <Form.Item wrapperCol={{ span: 24 }}>
            <div className="fixed bottom-10 right-10 z-50">
              <Row justify="end" gutter={16}>
                <Col>
                  <Button onClick={handleCancel}>
                    {t('common.cancel')}
                  </Button>
                </Col>
                <Col>
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button type="primary" onClick={handleConfirm} loading={confirmLoading}>
                      {t('common.confirm')}
                    </Button>
                  </PermissionWrapper>
                </Col>
              </Row>
            </div>
          </Form.Item>
        </Form>
      </Spin>
    </div>
  );
};

export default SettingsPage;
