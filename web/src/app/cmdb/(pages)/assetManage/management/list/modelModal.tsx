'use client';

import React, {
  useState,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Input, Button, Form, message, Radio, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import SelectIcon from './selectIcon';
import ModelIcon from '@/app/cmdb/components/model-icon';
import type { FormInstance } from 'antd';
import {
  ModelItem,
  ModelConfig,
  ModelIconItem,
} from '@/app/cmdb/types/assetManage';
import { deepClone } from '@/app/cmdb/utils/common';
const { Option } = Select;
import { useTranslation } from '@/utils/i18n';
import { useModelApi } from '@/app/cmdb/api';
import { useUserInfoContext } from '@/context/userInfo';

const APP_TOPO_LAYER_RADIO_CLASS =
  '!me-0 flex min-h-8 min-w-0 items-center';

interface ModelModalProps {
  onSuccess: (info?: unknown) => void;
  modelGroupList: Array<any>;
}

export interface ModelModalRef {
  showModal: (info: ModelConfig) => void;
}

const ModelModal = forwardRef<ModelModalRef, ModelModalProps>(
  ({ onSuccess, modelGroupList }, ref) => {
    const { createModel, updateModel } = useModelApi();
    const { selectedGroup } = useUserInfoContext();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const selectIconRef = useRef<any>(null);
    const [modelVisible, setModelVisible] = useState<boolean>(false);
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [modelInfo, setModelInfo] = useState<any>({});
    const [modelIcon, setModelIcon] = useState<ModelIconItem>({
      icn: '',
      model_id: '',
    });
    const [iconId, setIconId] = useState<any>('');

    const isBuiltinEdit = (info: Record<string, unknown> = modelInfo) => {
      const flag = info?.is_pre;
      if (typeof flag === 'string') {
        return flag.trim().toLowerCase() === 'true' || flag.trim() === '1';
      }
      return flag === true || flag === 1;
    };

    useEffect(() => {
      if (modelVisible) {
        formRef.current?.resetFields();

        const formData = { ...modelInfo };
        if (formData.group) {
          formData.group = Array.isArray(formData.group)
            ? formData.group
            : [formData.group];
        }
        if (type === 'add' && !formData.app_topo_layer) {
          formData.app_topo_layer = 'none';
        }
        formRef.current?.setFieldsValue(formData);

        if (type === 'add' && selectedGroup && !formData.group) {
          formRef.current?.setFieldValue('group', [selectedGroup.id]);
        }
      }
    }, [modelVisible, modelInfo]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, modelForm, subTitle, title }) => {
        const resolvedForm = modelForm || {};
        // 开启弹窗的交互
        setModelVisible(true);
        setSubTitle(subTitle);
        setType(type);
        setTitle(title);
        setModelIcon(
          type === 'edit'
            ? {
              model_id: resolvedForm.model_id,
              icn: resolvedForm.icn,
            }
            : { model_id: '', icn: '' }
        );
        setIconId(resolvedForm.icn || 'icon-cc-host');
        setModelInfo(resolvedForm);
      },
    }));

    const OperateModel = async (params: ModelItem) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add' ? 'successfullyAdded' : 'successfullyModified'
        );

        let requestParams = deepClone(params);
        if (type !== 'add') {
          requestParams = isBuiltinEdit()
            ? { app_topo_layer: params.app_topo_layer }
            : {
              classification_id: params.classification_id,
              model_name: params.model_name,
              icn: params.icn,
              group: Array.isArray(params.group) ? params.group : [params.group],
              app_topo_layer: params.app_topo_layer,
            };
        }

        if (type === 'add') {
          await createModel(requestParams);
        } else {
          await updateModel(modelInfo.model_id, requestParams);
        }

        message.success(msg);
        handleCancel();
        onSuccess(params);
      } catch (error) {
        console.log(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values: ModelItem) => {
        OperateModel({
          ...values,
          icn: iconId,
        });
      });
    };

    const handleCancel = () => {
      setModelVisible(false);
    };

    const onConfirmSelectIcon = (icon: string) => {
      setModelIcon({ icn: icon, model_id: modelInfo.model_id });
      setIconId(icon);
    };

    const onSelectIcon = () => {
      if (type === 'edit' && isBuiltinEdit()) {
        return;
      }
      selectIconRef.current?.showModal({
        title: t('Model.selectIcon'),
        defaultIcon: iconId,
      });
    };

    return (
      <div>
        <OperateModal
          title={title}
          subTitle={subTitle}
          visible={modelVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <div className="flex items-center justify-center flex-col">
            <div
              className={`flex items-center justify-center w-[80px] h-[80px] rounded-full border-solid border-[1px] border-[var(--color-border)] ${
                type === 'edit' && isBuiltinEdit()
                  ? 'cursor-default'
                  : 'cursor-pointer'
              }`}
              onClick={onSelectIcon}
            >
              <ModelIcon
                icon={modelIcon.icn}
                modelId={modelIcon.model_id}
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
            name="basic"
            layout="vertical"
          >
            <Form.Item<ModelItem>
              label={t('Model.modelGroup')}
              name="classification_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Select
                disabled={type === 'edit'}
                placeholder={t('common.selectTip')}
              >
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
            <Form.Item<ModelItem>
              label={t('organization')}
              name="group"
              rules={[{ required: true, message: t('required') }]}
            >
              <GroupTreeSelector
                disabled={type === 'edit' && isBuiltinEdit()}
                placeholder={t('common.selectTip')}
              />
            </Form.Item>
            <Form.Item<ModelItem>
              label={t('id')}
              name="model_id"
              rules={[
                { required: true, message: t('required') },
                {
                  pattern: /^[A-Za-z][A-Za-z0-9_]*$/,
                  message: t('Model.attrIdPattern'),
                },
              ]}
            >
              <Input
                disabled={type === 'edit'}
                placeholder={t('common.inputTip')}
              />
            </Form.Item>
            <Form.Item<ModelItem>
              label={t('name')}
              name="model_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input
                disabled={type === 'edit' && isBuiltinEdit()}
                placeholder={t('common.inputTip')}
              />
            </Form.Item>
            <Form.Item<ModelItem>
              label={t('Model.appTopoLayer')}
              name="app_topo_layer"
              rules={[{ required: true, message: t('required') }]}
            >
              <Radio.Group className="!grid w-full grid-cols-2 gap-x-8 gap-y-3">
                <Radio value="system" className={APP_TOPO_LAYER_RADIO_CLASS}>
                  {t('Model.appTopoLayerSystem')}
                </Radio>
                <Radio value="service" className={APP_TOPO_LAYER_RADIO_CLASS}>
                  {t('Model.appTopoLayerService')}
                </Radio>
                <Radio value="host" className={APP_TOPO_LAYER_RADIO_CLASS}>
                  {t('Model.appTopoLayerHost')}
                </Radio>
                <Radio value="appService" className={APP_TOPO_LAYER_RADIO_CLASS}>
                  {t('Model.appTopoLayerAppService')}
                </Radio>
                <Radio
                  value="infrastructure"
                  className={APP_TOPO_LAYER_RADIO_CLASS}
                >
                  {t('Model.appTopoLayerInfrastructure')}
                </Radio>
                <Radio value="none" className={APP_TOPO_LAYER_RADIO_CLASS}>
                  {t('Model.appTopoLayerNone')}
                </Radio>
              </Radio.Group>
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
ModelModal.displayName = 'ModelModal';
export default ModelModal;
