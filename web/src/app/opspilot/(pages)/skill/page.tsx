'use client';

import React, { useState, useEffect } from 'react';
import EntityList from '@/app/opspilot/components/entity-list';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';
import SkillCard from '@/app/opspilot/components/skill/skillCard';
import OperateModal from '@/components/operate-modal';
import { Skill } from '@/app/opspilot/types/skill';
import { useTranslation } from '@/utils/i18n';
import { Segmented, Button, Spin, Empty } from 'antd';
import Icon from '@/components/icon';
import { useSkillApi } from '@/app/opspilot/api/skill';

const SkillPage: React.FC = () => {
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false);
  const [activeTab, setActiveTab] = useState<number>(2);
  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const { t } = useTranslation();
  const { fetchSkillTemplates, createSkill } = useSkillApi();

  const iconTypeMapping: [string, string] = ['jiqirenjiaohukapian', 'jiqiren'];

  useEffect(() => {
    const fetchTemplates = async () => {
      if (isTemplateModalVisible) {
        setLoading(true);
        try {
          const data = await fetchSkillTemplates();
          setTemplates(data);
        } finally {
          setLoading(false);
        }
      }
    };

    fetchTemplates();
  }, [isTemplateModalVisible]);

  const handleCreateFromTemplate = (itemType: string) => {
    if (itemType === 'skill') {
      setIsTemplateModalVisible(true);
    }
  };

  const handleUseTemplate = async (template: any) => {
    setSubmitting(true);
    try {
      const payload = {
        name: template.name,
        introduction: template.introduction,
        team: template.team,
        skill_type: template.skill_type,
      };
      await createSkill(payload);
      setIsTemplateModalVisible(false);
      setRefreshKey((prev) => prev + 1);
    } finally {
      setSubmitting(false);
    }
  };

  const filteredTemplates = templates.filter((template) => template.skill_type === activeTab);

  return (
    <>
      <EntityList<Skill>
        key={refreshKey}
        endpoint="/opspilot/model_provider_mgmt/llm/"
        queryParams={{ is_template: 0 }}
        CardComponent={SkillCard}
        ModifyModalComponent={(props) => (
          <GenericModifyModal
            {...props}
            formType="skill"
          />
        )}
        itemTypeSingle="skill"
        onCreateFromTemplate={handleCreateFromTemplate}
      />
      <OperateModal
        width={850}
        title={t('skill.selectTemplate')}
        visible={isTemplateModalVisible}
        onCancel={() => !submitting && setIsTemplateModalVisible(false)}
        footer={null}
      >
        <Segmented
          options={[
            { label: t('skill.form.qaType'), value: 2 },
            { label: t('skill.form.toolsType'), value: 1 },
          ]}
          value={activeTab}
          onChange={(value) => !submitting && setActiveTab(value as number)}
          className="mb-4"
          disabled={submitting}
        />
        {loading ? (
          <div className="flex justify-center items-center min-h-[150px]">
            <Spin />
          </div>
        ) : (
          filteredTemplates.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 mb-4">
              {filteredTemplates.map((template, index) => (
                <div
                  key={template.id}
                  className={`shadow-md cursor-pointer rounded-xl relative overflow-hidden bg-[var(--color-bg)] group p-4 border-[0.5px] ${submitting ? 'pointer-events-none opacity-50' : ''}`}
                >
                  <div className="flex items-center">
                    <div className="flex justify-center items-center mr-4">
                      <Icon type={iconTypeMapping[index % iconTypeMapping.length]} className="text-2xl" />
                    </div>
                    <h3 className="font-bold text-sm">{template.name}</h3>
                  </div>
                  <div>
                    <p className="mt-3 mb-2 text-xs line-clamp-3 h-[50px] text-[var(--color-text-3)]">
                      {template.introduction}
                    </p>
                  </div>
                  <div
                    className="px-4 absolute bottom-[-40px] left-0 w-full text-center py-2 transition-all duration-300 opacity-0 group-hover:opacity-100 group-hover:bottom-0"
                  >
                    <Button type="primary" className="w-full mx-auto" onClick={() => handleUseTemplate(template)} disabled={submitting}>
                      {t('skill.useTemp')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty description={t('common.noData')} />
          )
        )}
      </OperateModal>
    </>
  );
};

export default SkillPage;
