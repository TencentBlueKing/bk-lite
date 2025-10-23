import { useState, useCallback, useEffect, useMemo, RefObject } from 'react';
import { FormInstance, message, Form, Select, Input, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useMlopsTaskApi from '@/app/mlops/api/task';
import { Option } from '@/app/mlops/types';
import { EditOutlined, MinusOutlined, PlusOutlined, UnorderedListOutlined, CloseOutlined, SaveOutlined } from '@ant-design/icons';
import { useRasaParamsToForm } from '@/app/mlops/hooks/task/useRasaParamsToForm';
import { PIPELINE_TYPE_OPTIONS, PIPELINE_OPTIONS, POLICIES_OPTIONS } from '@/app/mlops/constants';

interface ModalState {
  isOpen: boolean;
  type: string;
  title: string;
}

interface UseRasaFormProps {
  datasetOptions: Option[];
  activeTag: string[];
  onSuccess: () => void;
  formRef: RefObject<FormInstance>;
}

interface ConfigList {
  type?: string;
  select: string;
  config?: any
}

interface EditingItem {
  type: 'pipeline' | 'policies';
  index: number;
  componentName: string;
  formData: any;
}

export const useRasaForm = ({ datasetOptions, activeTag, onSuccess, formRef }: UseRasaFormProps) => {
  const { t } = useTranslation();
  const [key] = activeTag;
  // const formRef = useRef<FormInstance>(null);
  const { addRasaTrainTask, updateRasaPipelines } = useMlopsTaskApi();
  const [formData, setFormData] = useState<any>(null);
  const [pipeline, setPipeLine] = useState<ConfigList[]>([{ type: '', select: '', config: null }]);
  const [policies, setPolicies] = useState<ConfigList[]>([{ select: '', config: null }]);

  // 编辑状态管理
  const [editingItem, setEditingItem] = useState<EditingItem | null>(null);
  const [configFormData, setConfigFormData] = useState<any>({});

  // 使用RASA参数转换工具
  const { configToForm, formToConfig, generateStandaloneFormFields } = useRasaParamsToForm();

  // 使用 useMemo 优化静态数据
  const pipelineTypeOptions = useMemo(() => PIPELINE_TYPE_OPTIONS, []);
  const pipelineOptions = useMemo(() => PIPELINE_OPTIONS, []);
  const policiesOptions = useMemo(() => POLICIES_OPTIONS, []);

  const [modalState, setModalState] = useState<ModalState>({
    isOpen: false,
    type: 'add',
    title: 'addtask',
  });

  const [loadingState, setLoadingState] = useState<{
    confirm: boolean,
    dataset: boolean,
    select: boolean
  }>({
    confirm: false,
    dataset: false,
    select: false
  });

  useEffect(() => {
    if (modalState.isOpen) {
      initializeForm();
    }
  }, [modalState.isOpen])

  // 显示模态框
  const showModal = useCallback(({ type, title, form }: { type: string; title: string; form: any }) => {
    setLoadingState((prev) => ({ ...prev, select: false }));
    setFormData(form);
    setModalState({
      isOpen: true,
      type,
      title: title as string,
    });
  }, []);

  const initializeForm = () => {
    if (key !== 'rasa') return;
    try {
      if (modalState.type === 'add') {
        setPipeLine([{ type: '', select: '', config: null }]);
        setPolicies([{ select: '', config: null }]);
      } else {
        formRef.current?.setFieldsValue({
          name: formData?.name || '',
          dataset_id: formData?.datasets || []
        });
        if (formData?.config) {
          const { pipeline, policies } = formData?.config;
          setPipeLine(pipeline || [{ type: '', select: '', config: null }]);
          setPolicies(policies || [{ select: '', config: null }]);
        }
      }
    } catch (e) {
      console.log(e);
    }
  };

  // Pipeline 验证函数
  const validatePipeline = useCallback(() => {
    if (!pipeline || pipeline.length === 0) {
      return Promise.reject(new Error('请至少配置一个 pipeline 组件'));
    }

    for (let i = 0; i < pipeline.length; i++) {
      const item = pipeline[i];
      if (!item.type) {
        return Promise.reject(t(`common.selectMsg`));
      }
      if (!item.select) {
        return Promise.reject(t(`common.selectMsg`));
      }
    }

    return Promise.resolve();
  }, [pipeline, t]);

  // Policies 验证函数
  const validatePolicies = useCallback(() => {
    for (let i = 0; i < policies.length; i++) {
      const item = policies[i];
      if (!item.select) {
        return Promise.reject(t(`common.selectMsg`));
      }
    }

    return Promise.resolve();
  }, [policies, t]);

  // Pipeline类型选择事件
  const handlePipelineTypeChange = useCallback((value: string, index: number) => {
    setPipeLine(prev => {
      const newPipeline = [...prev];
      newPipeline[index] = { ...newPipeline[index], type: value, select: '' };
      return newPipeline;
    });
  }, []);

  // Pipeline组件选择事件
  const handlePipelineSelectChange = useCallback((value: string, index: number) => {
    setPipeLine(prev => {
      const newPipeline = [...prev];
      newPipeline[index] = { ...newPipeline[index], select: value };
      return newPipeline;
    });
  }, []);

  // Policies选择事件
  const handlePoliciesSelectChange = useCallback((value: string, index: number) => {
    setPolicies(prev => {
      const newPolicies = [...prev];
      newPolicies[index] = { ...newPolicies[index], select: value };
      return newPolicies;
    });
  }, []);

  // 配置表单组件
  const ConfigFormFields: React.FC<{
    componentName: string;
    initialValues?: any;
    onSave: (values: any) => void;
    configKey: string;
  }> = ({ componentName, initialValues, onSave }) => {
    const [localValues, setLocalValues] = useState<any>(initialValues || {});

    useEffect(() => {
      if (initialValues) {
        setLocalValues(initialValues);
      }
    }, [initialValues]);

    const handleFieldChange = (fieldName: string, value: any) => {
      setLocalValues((prev: any) => ({
        ...prev,
        [fieldName]: value
      }));
    };

    const handleSave = () => {
      onSave(localValues);
    };

    const fields = generateStandaloneFormFields(componentName, localValues, handleFieldChange);

    return (
      <div className='bg-[#f8f9fa] p-[6px] rounded-[6px] border border-[#e9ecef] my-1'>
        <div className='flex items-end w-full overflow-x-auto gap-3 whitespace-nowrap'>
          <div style={{ display: 'flex', gap: '5px', flexShrink: 0 }}>
            {fields}
          </div>
          <div style={{ marginLeft: 'auto', flexShrink: 0 }}>
            <Button
              size="small"
              icon={<SaveOutlined />}
              onClick={handleSave}
            />
          </div>
        </div>
      </div>
    );
  };

  // 编辑按钮点击事件
  const handleEditClick = useCallback((type: string, index: number) => {
    const currentItem = type === 'pipeline' ? pipeline[index] : policies[index];
    const componentName = currentItem.select;

    if (!componentName) {
      message.warning(t(`common.selectMsg`));
      return;
    }

    setEditingItem({
      type: type as 'pipeline' | 'policies',
      index,
      componentName,
      formData: currentItem.config || {}
    });

    const config = currentItem.config || {};
    const formData = configToForm(componentName, config);
    setConfigFormData(formData);
  }, [pipeline, policies, configToForm, t]);

  // 保存配置
  const handleConfigSave = useCallback((formValues: any) => {
    if (!editingItem) return;

    const config = formToConfig(editingItem.componentName, formValues);

    if (editingItem.type === 'pipeline') {
      setPipeLine(prev => {
        const newPipeline = [...prev];
        newPipeline[editingItem.index] = {
          ...newPipeline[editingItem.index],
          config
        };
        return newPipeline;
      });
    } else {
      setPolicies(prev => {
        const newPolicies = [...prev];
        newPolicies[editingItem.index] = {
          ...newPolicies[editingItem.index],
          config
        };
        return newPolicies;
      });
    }

    setEditingItem(null);
    setConfigFormData({});
  }, [editingItem, formToConfig]);

  // 取消编辑
  const handleConfigCancel = useCallback(() => {
    setEditingItem(null);
    setConfigFormData({});
  }, []);

  // 添加按钮点击事件
  const handleAddClick = useCallback((type: string, index: number) => {
    if (type === 'pipeline') {
      setPipeLine(prev => {
        const newPipeline = [...prev];
        newPipeline.splice(index + 1, 0, { type: '', select: '', config: null });
        return newPipeline;
      });
    } else {
      setPolicies(prev => {
        const newPolicies = [...prev];
        newPolicies.splice(index + 1, 0, { select: '', config: null });
        return newPolicies;
      });
    }
  }, []);

  // 删除按钮点击事件
  const handleRemoveClick = useCallback((type: string, index: number) => {
    if (type === 'pipeline') {
      setPipeLine(prev => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev);
    } else {
      setPolicies(prev => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev);
    }
  }, []);

  // 拖拽开始事件
  const handleDragStart = useCallback((e: React.DragEvent, type: string, index: number) => {
    e.dataTransfer.setData('text/plain', JSON.stringify({ type, index }));
    e.dataTransfer.effectAllowed = 'move';
  }, []);

  // 拖拽悬停事件
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  // 拖拽放置事件
  const handleDrop = useCallback((e: React.DragEvent, type: string, targetIndex: number) => {
    e.preventDefault();
    const dragData = JSON.parse(e.dataTransfer.getData('text/plain'));
    const { type: dragType, index: dragIndex } = dragData;

    if (dragType !== type || dragIndex === targetIndex) return;

    if (type === 'pipeline') {
      setPipeLine(prev => {
        const newPipeline = [...prev];
        const draggedItem = newPipeline[dragIndex];
        newPipeline.splice(dragIndex, 1);
        newPipeline.splice(targetIndex, 0, draggedItem);
        return newPipeline;
      });
    } else {
      setPolicies(prev => {
        const newPolicies = [...prev];
        const draggedItem = newPolicies[dragIndex];
        newPolicies.splice(dragIndex, 1);
        newPolicies.splice(targetIndex, 0, draggedItem);
        return newPolicies;
      });
    }
  }, []);

  const handleSubmit = async () => {
    setLoadingState(prev => ({ ...prev, confirm: true }));
    try {
      if (!formRef) return;
      const value = await formRef.current?.validateFields();
      const datasets: number[] = value.dataset_id || [];
      const params = {
        name: value.name,
        datasets: datasets,
        dataset_names: datasetOptions.filter((item) => datasets.includes(item.value as number)).map((item) => item.label),
        config: {
          pipeline,
          policies
        }
      }
      if (modalState.type === 'add') {
        await addRasaTrainTask(params);
        message.success(t(`common.addSuccess`));
      } else {
        await updateRasaPipelines(formData.id, params);
        message.success(t(`common.updateSuccess`));
      }
      onSuccess();
      setModalState((prev) => ({ ...prev, isOpen: false }));
    } catch (e) {
      console.log(e);
      message.error(t(`common.valFailed`));
    } finally {
      setLoadingState((prev) => ({ ...prev, confirm: false }));
    }
  };

  const handleCancel = () => {
    setModalState({
      isOpen: false,
      type: 'add',
      title: 'addtask',
    });
    setPipeLine([{ type: '', select: '', config: null }]);
    setPolicies([{ select: '', config: null }]);
    formRef.current?.resetFields();
  };

  const renderFormContent = useCallback(() => {
    if (key !== 'rasa') return;
    return (
      <>
        <Form.Item
          name='name'
          label={t('common.name')}
          rules={[{ required: true, message: t('common.inputMsg') }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name='dataset_id'
          label={t('traintask.datasets')}
          rules={[{ required: true, message: t('traintask.selectDatasets') }]}
        >
          <Select mode='multiple' placeholder={t('traintask.selectDatasets')} options={datasetOptions} />
        </Form.Item>
        <Form.Item
          name="pipeline"
          label="pipeline"
          rules={[{
            required: true,
            validator: validatePipeline
          }]}
        >
          <div>
            {pipeline.map((item, index) => (
              <div key={index}>
                <div
                  className='flex gap-1 pl-1 mb-2'
                  draggable
                  onDragStart={(e) => handleDragStart(e, 'pipeline', index)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, 'pipeline', index)}
                  style={{
                    cursor: 'move',
                    borderRadius: '4px',
                    padding: '4px'
                  }}
                >
                  <UnorderedListOutlined style={{ cursor: 'move', color: '#1890ff' }} />
                  <Select
                    style={{ width: 120 }}
                    options={pipelineTypeOptions}
                    placeholder={t(`common.type`)}
                    value={item.type || undefined}
                    onChange={(value) => handlePipelineTypeChange(value, index)}
                  />
                  <Select
                    style={{ width: 200 }}
                    options={item?.type ? pipelineOptions[item.type] : []}
                    placeholder={t(`common.selectMsg`)}
                    value={item.select || undefined}
                    onChange={(value) => handlePipelineSelectChange(value, index)}
                  />
                  {editingItem?.type === 'pipeline' && editingItem?.index === index ? (
                    <Button
                      icon={<CloseOutlined />}
                      onClick={handleConfigCancel}
                    />
                  ) : (
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => handleEditClick('pipeline', index)}
                    />
                  )}
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => handleAddClick('pipeline', index)}
                  />
                  {!!index && (
                    <Button
                      icon={<MinusOutlined />}
                      onClick={() => handleRemoveClick('pipeline', index)}
                    />
                  )}
                </div>
                {editingItem?.type === 'pipeline' && editingItem?.index === index && (
                  <ConfigFormFields
                    componentName={editingItem.componentName}
                    initialValues={configFormData}
                    onSave={handleConfigSave}
                    configKey={`pipeline_${index}`}
                  />
                )}
              </div>
            ))}
          </div>
        </Form.Item>
        <Form.Item
          name="policies"
          label="policies"
          rules={[{
            required: true,
            validator: validatePolicies
          }]}
        >
          <div>
            {policies.map((item, index) => (
              <div key={index}>
                <div
                  className='flex gap-1 pl-1 mb-2'
                  draggable
                  onDragStart={(e) => handleDragStart(e, 'policies', index)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, 'policies', index)}
                  style={{
                    cursor: 'move',
                    borderRadius: '4px',
                    padding: '4px'
                  }}
                >
                  <UnorderedListOutlined style={{ cursor: 'move', color: '#1890ff' }} />
                  <Select
                    style={{ width: 320 }}
                    options={policiesOptions}
                    placeholder={t(`common.selectMsg`)}
                    value={item.select || undefined}
                    onChange={(value) => handlePoliciesSelectChange(value, index)}
                  />
                  {editingItem?.type === 'policies' && editingItem?.index === index ? (
                    <Button
                      icon={<CloseOutlined />}
                      onClick={handleConfigCancel}
                    />
                  ) : (
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => handleEditClick('policies', index)}
                    />
                  )}
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => handleAddClick('policies', index)}
                  />
                  {!!index && (
                    <Button
                      icon={<MinusOutlined />}
                      onClick={() => handleRemoveClick('policies', index)}
                    />
                  )}
                </div>
                {editingItem?.type === 'policies' && editingItem?.index === index && (
                  <ConfigFormFields
                    componentName={editingItem.componentName}
                    initialValues={configFormData}
                    onSave={handleConfigSave}
                    configKey={`policies_${index}`}
                  />
                )}
              </div>
            ))}
          </div>
        </Form.Item>
      </>
    )
  }, [t, pipeline, policies, pipelineTypeOptions, pipelineOptions, policiesOptions, datasetOptions, handlePipelineTypeChange, handlePipelineSelectChange, handlePoliciesSelectChange, handleEditClick, handleAddClick, handleRemoveClick, handleDragStart, handleDragOver, handleDrop, editingItem, configFormData, handleConfigSave, handleConfigCancel, ConfigFormFields, validatePipeline, validatePolicies]);

  return {
    renderFormContent,
    modalState,
    formRef,
    loadingState,
    showModal,
    handleCancel,
    handleSubmit
  }
};
