import React, { useState, useEffect, useRef } from 'react';
import { Form, Input, message, Tag, Tooltip, Button, InputRef } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { PlusOutlined, SearchOutlined } from '@ant-design/icons';
import { useRoleApi } from '@/app/system-manager/api/application';
import OperateModal from '@/components/operate-modal';
import Icon from '@/components/icon';
import { IconGlyph, ApplicationFormModalProps } from '@/app/system-manager/types/application';

const { TextArea } = Input;

const ApplicationFormModal: React.FC<ApplicationFormModalProps> = ({
  visible,
  initialData,
  isEdit = false,
  onClose,
  onSuccess
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { addApplication, updateApplication } = useRoleApi();
  const [loading, setLoading] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [inputVisible, setInputVisible] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<any>(null);
  const [iconSelectorVisible, setIconSelectorVisible] = useState(false);
  const [selectedIcon, setSelectedIcon] = useState<string | undefined>(undefined);
  const [searchValue, setSearchValue] = useState('');
  const [icons, setIcons] = useState<IconGlyph[]>([]);
  const [filteredIcons, setFilteredIcons] = useState<IconGlyph[]>([]);
  const iconSelectorRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<InputRef>(null);
  const isBuiltIn = initialData?.is_build_in;

  useEffect(() => {
    const loadIconData = async () => {
      try {
        const response = await fetch('/iconfont.json');
        if (!response.ok) {
          throw new Error(`Failed to fetch icon data: ${response.status}`);
        }
        const iconData = await response.json();
        setIcons(iconData.glyphs || []);
      } catch (error) {
        console.error("Error loading icon data:", error);
        setIcons([]);
      }
    };
    
    loadIconData();
  }, []);

  useEffect(() => {
    if (iconSelectorVisible) {
      setFilteredIcons(
        icons.filter(icon => 
          !searchValue || 
          icon.name.toLowerCase().includes(searchValue.toLowerCase()) ||
          icon.font_class.toLowerCase().includes(searchValue.toLowerCase())
        )
      );
    }
  }, [searchValue, icons, iconSelectorVisible]);

  useEffect(() => {
    if (iconSelectorVisible && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100);
    }
  }, [iconSelectorVisible]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (iconSelectorRef.current && !iconSelectorRef.current.contains(event.target as Node)) {
        setIconSelectorVisible(false);
      }
    };

    if (iconSelectorVisible) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [iconSelectorVisible]);

  useEffect(() => {
    if (visible && initialData) {
      form.setFieldsValue({
        name: initialData.name,
        display_name: initialData.display_name,
        description: initialData.description,
        url: initialData.url,
        icon: initialData.icon
      });
      setSelectedIcon(initialData.icon || undefined);
      setTags(initialData.tags || []);
    } else if (visible) {
      Promise.resolve().then(() => {
        form.resetFields();
        setSelectedIcon(undefined);
        setTags([]);
      });
    }
  }, [visible, initialData, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      const applicationData = {
        name: values.name,
        display_name: values.display_name,
        description: values.description,
        url: values.url,
        icon: selectedIcon || null,
        tags: tags
      };
      if (isEdit && initialData?.name) {
        await updateApplication({...applicationData, id: initialData.id});
        message.success(t('common.updateSuccess'));
      } else {
        await addApplication(applicationData);
        message.success(t('common.saveSuccess'));
      }

      onSuccess();
    } catch (error) {
      console.error('Form submission error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleIconSelect = (iconName: string) => {
    setSelectedIcon(iconName);
    form.setFieldsValue({ icon: iconName });
    setIconSelectorVisible(false);
  };

  const toggleIconSelector = () => {
    setIconSelectorVisible(!iconSelectorVisible);
    if (!iconSelectorVisible) {
      setSearchValue('');
      setFilteredIcons(icons);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchValue(e.target.value);
  };

  const showInput = () => {
    setInputVisible(true);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  const handleInputConfirm = () => {
    if (inputValue && !tags.includes(inputValue) && tags.length < 8) {
      setTags([...tags, inputValue]);
    }
    setInputVisible(false);
    setInputValue('');
  };

  const handleTagClose = (removedTag: string) => {
    const newTags = tags.filter(tag => tag !== removedTag);
    setTags(newTags);
  };

  const isValidURL = (url: string): boolean => {
    if (url.startsWith('/')) {
      return true;
    }
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  return (
    <OperateModal
      title={isEdit ? t('common.edit') : t('common.edit')}
      open={visible}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      maskClosable={false}
      width={600}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initialData || {}}
      >
        <div className="relative mb-4 flex justify-center">
          <Button 
            onClick={toggleIconSelector}
            className="flex items-center justify-center text-left w-14 h-14 px-4 py-1"
          >
            {selectedIcon ? (
              <div className="flex items-center">
                <Icon type={selectedIcon} className="text-lg" />
              </div>
            ) : (
              <span className="text-xs">{t('system.application.selectIcon')}</span>
            )}
          </Button>
          
          {iconSelectorVisible && (
            <div 
              ref={iconSelectorRef}
              className="absolute z-50 left-0 right-0 mt-10 bg-white border border-gray-200 rounded-md shadow-lg p-4 max-h-[300px] overflow-y-auto"
            >
              <Input
                ref={searchInputRef}
                placeholder={t('system.application.searchIcon')}
                prefix={<SearchOutlined />}
                value={searchValue}
                onChange={handleSearchChange}
                className="mb-3"
                allowClear
              />
              
              {filteredIcons.length > 0 ? (
                <div className="grid grid-cols-6 gap-2">
                  {filteredIcons.map((icon) => (
                    <Tooltip key={icon.font_class} title={icon.name}>
                      <div 
                        className={`flex flex-col items-center justify-center p-2 cursor-pointer hover:bg-gray-100 rounded transition-colors border border-transparent hover:border-gray-300 ${
                          selectedIcon === icon.font_class ? 'bg-blue-50 border-blue-300' : ''
                        }`}
                        onClick={() => handleIconSelect(icon.font_class)}
                      >
                        <Icon 
                          type={icon.font_class} 
                          className="text-xl mb-1 w-[1em] h-[1em] align-[-0.15em] fill-current overflow-hidden"
                        />
                      </div>
                    </Tooltip>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-gray-500">
                  {t('system.application.noIconsFound')}
                </div>
              )}
            </div>
          )}
        </div>

        <Form.Item
          name="name"
          label={t('system.application.id')}
          rules={[
            { required: true, message: `${t('common.inputMsg')}${t('system.application.id')}` },
            { pattern: /^[a-zA-Z0-9_-]+$/, message: t('system.application.idFormat') }
          ]}
          tooltip={t('system.application.idTooltip')}
        >
          <Input placeholder={`${t('common.inputMsg')}${t('system.application.id')}`} disabled={isEdit || isBuiltIn} />
        </Form.Item>

        <Form.Item
          name="display_name"
          label={t('system.application.name')}
          rules={[
            { required: true, message: `${t('common.inputMsg')}${t('system.application.name')}` },
            { max: 50, message: t('system.application.nameMaxLength') }
          ]}
        >
          <Input placeholder={`${t('common.inputMsg')}${t('system.application.name')}`} disabled={isBuiltIn} />
        </Form.Item>

        <Form.Item
          name="url"
          label={t('system.application.url')}
          rules={[
            { required: true, message: `${t('common.inputMsg')}${t('system.application.url')}` },
            { 
              validator: (_, value) => {
                if (!value || isValidURL(value)) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error(t('system.application.urlInvalid')));
              } 
            }
          ]}
        >
          <Input placeholder={`${t('common.inputMsg')}${t('system.application.url')}`} />
        </Form.Item>

        <Form.Item
          label={t('system.application.tags')}
          tooltip={t('system.application.tagsTooltip')}
        >
          <div className="flex flex-wrap gap-2 mb-2">
            {tags.map((tag, index) => (
              <Tag
                key={index}
                closable={!isBuiltIn}
                onClose={!isBuiltIn ? () => handleTagClose(tag) : undefined}
              >
                {tag}
              </Tag>
            ))}
            {inputVisible && !isBuiltIn && (
              <Input
                ref={inputRef}
                type="text"
                size="small"
                className="w-[78px]"
                value={inputValue}
                onChange={handleInputChange}
                onBlur={handleInputConfirm}
                onPressEnter={handleInputConfirm}
                maxLength={6}
              />
            )}
            {!inputVisible && !isBuiltIn && tags.length < 8 && (
              <Tag className="cursor-pointer" onClick={showInput}>
                <PlusOutlined /> {t('system.application.addTag')}
              </Tag>
            )}
            {!isBuiltIn && tags.length >= 8 && (
              <Tooltip title={t('system.application.maxTagsReached')}>
                <Tag className="cursor-not-allowed opacity-50">
                  <PlusOutlined /> {t('system.application.addTag')}
                </Tag>
              </Tooltip>
            )}
          </div>
          <div className="text-xs text-gray-400">
            {t('system.application.tagsHelp')}
          </div>
        </Form.Item>

        <Form.Item
          name="description"
          label={t('system.application.description')}
          rules={[
            { max: 500, message: t('system.application.descriptionMaxLength') }
          ]}
        >
          <TextArea
            placeholder={`${t('common.inputMsg')}${t('system.application.description')}`}
            autoSize={{ minRows: 3, maxRows: 6 }}
            disabled={isBuiltIn}
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
};

export default ApplicationFormModal;
