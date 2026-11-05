'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Modal, message } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import { useTranslation } from '@/utils/i18n';
import { useCarouselApi } from '@/app/ops-analysis/api/carousel';
import type { CarouselDetail, CarouselSummary } from '@/app/ops-analysis/types/carousel';
import { CAROUSEL_DEFAULT_DWELL_SECONDS } from '@/app/ops-analysis/utils/carouselPlayer';

interface CarouselInfoModalProps {
  open: boolean;
  carousel?: CarouselSummary | null;
  onClose: () => void;
  beforeSubmit?: () => Promise<boolean>;
  onCreated: (detail: CarouselDetail) => void;
  onUpdated: () => void;
}

const CarouselInfoModal: React.FC<CarouselInfoModalProps> = ({
  open,
  carousel,
  onClose,
  beforeSubmit,
  onCreated,
  onUpdated,
}) => {
  const { t } = useTranslation();
  const { selectedGroup, groupTree } = useUserInfoContext();
  const { createCarousel, updateCarousel } = useCarouselApi();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const editing = Boolean(carousel);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      name: carousel?.name || '',
      desc: carousel?.desc || '',
      groups: carousel?.groups?.length
        ? carousel.groups
        : (selectedGroup?.id ? [Number(selectedGroup.id)] : []),
    });
  }, [carousel, form, open, selectedGroup?.id]);

  const close = () => {
    form.resetFields();
    onClose();
  };

  const submit = async () => {
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    if (!carousel && beforeSubmit && !(await beforeSubmit())) return;
    const payload = {
      name: String(values.name).trim(),
      desc: values.desc || '',
      groups: (values.groups || []).map((groupId: number) => Number(groupId)),
    };
    setSaving(true);
    try {
      if (carousel) {
        await updateCarousel(carousel.id, payload);
        close();
        onUpdated();
        return;
      }
      const created = await createCarousel({
        ...payload,
        default_dwell_seconds: CAROUSEL_DEFAULT_DWELL_SECONDS,
        items: [],
      });
      close();
      onCreated(created);
    } catch {
      message.error(t('common.operationFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={editing ? t('opsCarousel.editBasic') : t('opsCarousel.newList')}
      open={open}
      centered
      width={520}
      onCancel={close}
      footer={[
        <Button key="cancel" onClick={close}>
          {t('common.cancel')}
        </Button>,
        <Button key="submit" type="primary" loading={saving} onClick={() => { void submit(); }}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Form form={form} className="mt-5" layout="vertical">
        <Form.Item
          name="name"
          label={t('opsAnalysisSidebar.nameLabel')}
          rules={[{ required: true, whitespace: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('opsAnalysisSidebar.inputPlaceholder')} maxLength={128} />
        </Form.Item>
        <Form.Item
          name="groups"
          label={t('opsCarousel.ownerOrg')}
          rules={[{ required: true, message: `${t('common.selectMsg')}${t('opsCarousel.ownerOrg')}` }]}
        >
          <GroupTreeSelect
            treeData={convertGroupTreeToTreeSelectData(groupTree || [])}
            placeholder={`${t('common.selectMsg')}${t('opsCarousel.ownerOrg')}`}
            multiple
            mode="ownership"
          />
        </Form.Item>
        <Form.Item name="desc" label={t('opsAnalysisSidebar.descLabel')}>
          <Input.TextArea
            autoSize={{ minRows: 3 }}
            placeholder={`${t('common.inputMsg')} ${t('opsAnalysisSidebar.descLabel')}`}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CarouselInfoModal;
