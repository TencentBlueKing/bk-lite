'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Select, Checkbox } from 'antd';
import Image from 'next/image';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import SelectIcon from './selectIcon';
import { getIconUrl } from '@/app/cmdb/utils/common';
import type { FormInstance } from 'antd';
const { Option } = Select;
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useRouter } from 'next/navigation';

interface CopyModelModalProps {
  onSuccess: (info?: unknown) => void;
  modelGroupList: Array<any>;
}

export interface CopyModelModalRef {
  showModal: (info: any) => void;
}

interface CopyModelFormData {
  classification_id: string;
  group: string | string[];
  model_id: string;
  model_name: string;
  copy_mode: string[];
}

const CopyModelModal = forwardRef<CopyModelModalRef, CopyModelModalProps>(
  ({ onSuccess, modelGroupList }, ref) => {
    const { copyModel } = useModelApi();
    const { t } = useTranslation();
    const router = useRouter();
    const formRef = useRef<FormInstance>(null);
    const selectIconRef = useRef<any>(null);
    const [modalVisible, setModalVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [sourceModel, setSourceModel] = useState<any>({});
    const [modelIcon, setModelIcon] = useState<any>('');
    const [iconId, setIconId] = useState<any>('');

    useEffect(() => {
      if (modalVisible) {
        formRef.current?.resetFields();

        // 设置默认值：继承源模型的分组和分类
        if (sourceModel) {
          formRef.current?.setFieldsValue({
            classification_id: sourceModel.classification_id,
            group: sourceModel.group,
            copy_mode: ['attributes'], // 默认选择属性
          });
        }
      }
    }, [modalVisible, sourceModel]);

    useImperativeHandle(ref, () => ({
      showModal: (model: any) => {
        setModalVisible(true);
        setSourceModel(model);
        const icon = getIconUrl(model);
        setModelIcon(icon);
        setIconId(model.icn || 'icon-cc-host');
      },
    }));

    const handleCopyModel = async (params: CopyModelFormData) => {
      try {
        setConfirmLoading(true);

        const { copy_mode, ...restParams } = params;

        // 验证：必须选择至少一个复制模式
        if (!copy_mode || copy_mode.length === 0) {
          message.error(t('Model.selectCopyMode'));
          return;
        }

        // 构建请求参数
        const requestParams = {
          new_model_id: restParams.model_id,
          new_model_name: restParams.model_name,
          classification_id: restParams.classification_id,
          group: Array.isArray(params.group) ? params.group : [params.group],
          copy_attributes: copy_mode.includes('attributes'),
          copy_relationships: copy_mode.includes('relationships'),
          icn: iconId,
        };

        const response = await copyModel(sourceModel.model_id, requestParams);

        message.success(t('successfullyAdded'));
        handleCancel();
        onSuccess(params);

        // 跳转到新模型的详情页面
        if (response && response.model_id) {
          const queryParams = new URLSearchParams({
            model_id: response.model_id,
            model_name: params.model_name,
            icn: iconId,
            classification_id: params.classification_id,
            is_pre: 'false',
          }).toString();
          router.push(
            `/cmdb/assetManage/management/detail/attributes?${queryParams}`
          );
        }
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values: CopyModelFormData) => {
        handleCopyModel(values);
      });
    };

    const handleCancel = () => {
      setModalVisible(false);
    };

    const onConfirmSelectIcon = (icon: string) => {
      const objId = icon.replace('cc-', '');
      const _iconId = 'icon-' + icon;
      setModelIcon(
        getIconUrl({
          icn: _iconId,
          model_id: objId,
        })
      );
      setIconId(_iconId);
    };

    const onSelectIcon = () => {
      selectIconRef.current?.showModal({
        title: t('Model.selectIcon'),
        defaultIcon: iconId,
      });
    };

    return (
      <div>
        <OperateModal
          title={t('Model.copyModel')}
          visible={modalVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
              <Button
                type="primary"
                className="ml-[10px]"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
            </div>
          }
        >
          <div className="flex items-center justify-center flex-col">
            <div
              className="flex items-center justify-center cursor-pointer w-[80px] h-[80px] rounded-full border-solid border-[1px] border-[var(--color-border)]"
              onClick={onSelectIcon}
            >
              <Image
                src={modelIcon}
                className="block w-auto h-10"
                alt={t('picture')}
                width={60}
                height={60}
              />
            </div>
            <span className="text-[var(--color-text-3)] mt-[10px] mb-[20px]">
              {t('Model.selectIcon')}
            </span>
          </div>
          <Form
            ref={formRef}
            name="copy_model_form"
            labelCol={{ span: 6 }}
            wrapperCol={{ span: 18 }}
          >
            <Form.Item<CopyModelFormData>
              label={t('Model.modelGroup')}
              name="classification_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select placeholder={t('common.selectTip')}>
                {modelGroupList.map((item) => {
                  return (
                    <Option
                      value={item.classification_id}
                      key={item.classification_id}
                    >
                      {item.classification_name}
                    </Option>
                  );
                })}
              </Select>
            </Form.Item>
            <Form.Item<CopyModelFormData>
              label={t('organization')}
              name="group"
              rules={[{ required: true, message: t('required') }]}
            >
              <GroupTreeSelector placeholder={t('common.selectTip')} />
            </Form.Item>
            <Form.Item<CopyModelFormData>
              label={t('id')}
              name="model_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
            <Form.Item<CopyModelFormData>
              label={t('name')}
              name="model_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
            <Form.Item<CopyModelFormData>
              label={t('Model.copyMode')}
              name="copy_mode"
              rules={[
                {
                  required: true,
                  message: t('Model.selectCopyMode'),
                },
              ]}
            >
              <Checkbox.Group>
                <div className="flex gap-[16px]">
                  <Checkbox value="attributes">
                    {t('Model.attributes')}
                  </Checkbox>
                  <Checkbox value="relationships">
                    {t('Model.relationships')}
                  </Checkbox>
                </div>
              </Checkbox.Group>
            </Form.Item>
          </Form>
        </OperateModal>
        <SelectIcon
          ref={selectIconRef}
          onSelect={(icon) => onConfirmSelectIcon(icon)}
        />
      </div>
    );
  }
);

CopyModelModal.displayName = 'CopyModelModal';
export default CopyModelModal;
