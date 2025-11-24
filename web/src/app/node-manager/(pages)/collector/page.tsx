'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Menu, Input, Button, message, Modal, Tag, Segmented } from 'antd';
import useApiClient from '@/utils/request';
import useNodeManagerApi from '@/app/node-manager/api';
import EntityList from '@/components/entity-list/index';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { CardItem } from '@/app/node-manager/types';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import { ModalRef } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';
import { useCollectorMenuItem } from '@/app/node-manager/hooks/collector';
const { Search } = Input;
const { confirm } = Modal;

const Collector = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCollectorlist, deleteCollector, getNodeStateEnum } =
    useNodeManagerApi();
  const menuItem = useCollectorMenuItem();
  const modalRef = useRef<ModalRef>(null);
  const [collectorCards, setCollectorCards] = useState<CardItem[]>([]);
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [appTags, setAppTags] = useState<any[]>([]);
  const [systemTags, setSystemTags] = useState<any[]>([]);
  const [selectedAppTag, setSelectedAppTag] = useState<string>('');
  const [selectedSystemTags, setSelectedSystemTags] = useState<string[]>([]);
  const [tagEnum, setTagEnum] = useState<Record<string, any>>({});

  useEffect(() => {
    if (!isLoading) {
      initData();
    }
  }, [isLoading]);

  const initData = () => {
    setLoading(true);
    getTags()
      .then((data) => {
        const { apps, tagEnum: newTagEnum } = data;
        const defaultAppTag = apps && apps.length > 0 ? apps[0].value : '';
        setSelectedAppTag(defaultAppTag);
        fetchCollectorlist({
          searchValue: '',
          appTag: defaultAppTag,
          sysTags: [],
          tagEnum: newTagEnum,
        });
      })
      .catch(() => {
        setLoading(false);
      });
  };

  const navigateToCollectorDetail = (item: CardItem) => {
    router.push(`
      /node-manager/collector/detail?id=${item.id}&name=${item.name}&introduction=${item.description}&system=${item.tagList[0]}&icon=${item.icon}`);
  };

  const getTags = async () => {
    const res = await getNodeStateEnum();
    if (res?.tag) {
      const tagData = res.tag;
      const apps: any[] = [];
      const systems: any[] = [];
      Object.keys(tagData).forEach((key) => {
        const item = tagData[key];
        if (item.is_app) {
          apps.push({ label: item.name, value: key });
        } else {
          systems.push({ label: item.name, value: key });
        }
      });
      setAppTags(apps);
      setSystemTags(systems);
      setTagEnum(tagData);
      return { apps, tagEnum: tagData };
    }
    return { apps: [], tagEnum: {} };
  };

  const handleResult = (res: any, enumMap?: Record<string, any>) => {
    const currentTagEnum = enumMap || tagEnum;
    const filter = res.filter((item: any) => !item.controller_default_run);
    const tempdata = filter.map((item: any) => {
      const tagList = item.tags || [];
      const displayTags = tagList.map((tag: string) => {
        return currentTagEnum[tag]?.name || tag;
      });
      return {
        id: item.id,
        name: item.name,
        service_type: item.service_type,
        executable_path: item.executable_path,
        execute_parameters: item.execute_parameters,
        description: item.introduction || '--',
        icon: item.icon || 'caijiqizongshu',
        tagList: displayTags,
        originalTags: tagList,
      };
    });
    setCollectorCards(tempdata);
  };

  const fetchCollectorlist = async (params: {
    searchValue?: string;
    appTag?: string;
    sysTags?: string[];
    tagEnum?: Record<string, any>;
  }) => {
    const { searchValue, appTag, sysTags, tagEnum: enumMap } = params;
    const requestParams: any = { name: searchValue };
    const tagsArray: string[] = [];
    const currentAppTag = appTag !== undefined ? appTag : selectedAppTag;
    const currentSysTags = sysTags !== undefined ? sysTags : selectedSystemTags;
    if (currentAppTag) {
      tagsArray.push(currentAppTag);
    }
    if (currentSysTags.length > 0) {
      tagsArray.push(...currentSysTags);
    }
    if (tagsArray.length > 0) {
      requestParams.tags = tagsArray.join(',');
    }
    try {
      setLoading(true);
      const res = await getCollectorlist(requestParams);
      handleResult(res, enumMap);
    } finally {
      setLoading(false);
    }
  };

  const openModal = (config: any) => {
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form: config?.form,
      key: config?.key,
    });
  };

  const handleSubmit = (type?: string) => {
    if (type === 'upload') return;
    fetchCollectorlist({ searchValue: search });
  };

  const handleDelete = (id: string) => {
    confirm({
      title: t(`common.delete`),
      content: t(`node-manager.packetManage.deleteInfo`),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return new Promise(async (resolve) => {
          try {
            await deleteCollector({ id });
            message.success(t('common.successfullyDeleted'));
            fetchCollectorlist({ searchValue: search });
          } finally {
            return resolve(true);
          }
        });
      },
    });
  };

  const menuActions = useCallback(
    (data: any) => {
      return (
        <Menu onClick={(e) => e.domEvent.preventDefault()}>
          {menuItem.map((item) => {
            return (
              <Menu.Item
                key={item.key}
                className="!p-0"
                onClick={() =>
                  openModal({ ...item.config, form: data, key: 'collector' })
                }
              >
                <PermissionWrapper
                  requiredPermissions={[item.role]}
                  className="!block"
                >
                  <Button type="text" className="w-full">
                    {item.title}
                  </Button>
                </PermissionWrapper>
              </Menu.Item>
            );
          })}
          <Menu.Item className="!p-0" onClick={() => handleDelete(data.id)}>
            <PermissionWrapper
              requiredPermissions={['Delete']}
              className="!block"
            >
              <Button type="text" className="w-full">
                {t(`common.delete`)}
              </Button>
            </PermissionWrapper>
          </Menu.Item>
        </Menu>
      );
    },
    [menuItem]
  );

  const handleSystemTagClick = (tag: string) => {
    const newSelectedTags = selectedSystemTags.includes(tag)
      ? selectedSystemTags.filter((t: string) => t !== tag)
      : [...selectedSystemTags, tag];
    setSelectedSystemTags(newSelectedTags);
    fetchCollectorlist({
      searchValue: search,
      appTag: selectedAppTag,
      sysTags: newSelectedTags,
    });
  };

  const handleAppTagChange = (value: string | number) => {
    const newAppTag = value as string;
    setSelectedAppTag(newAppTag);
    fetchCollectorlist({
      searchValue: search,
      appTag: newAppTag,
      sysTags: selectedSystemTags,
    });
  };

  const ifOpenAddModal = () => {
    return {
      openModal: () =>
        openModal({
          title: t('node-manager.collector.addCollector'),
          type: 'add',
          form: {},
        }),
    };
  };

  const onSearch = (searchValue: string) => {
    setSearch(searchValue);
    fetchCollectorlist({ searchValue });
  };

  return (
    <div className="h-[calc(100vh-88px)] w-full">
      <EntityList
        data={collectorCards}
        loading={loading}
        menuActions={(value) => menuActions(value)}
        filter={false}
        search={false}
        operateSection={
          <div className="w-full">
            {appTags.length > 0 && (
              <Segmented
                options={appTags}
                value={selectedAppTag}
                onChange={handleAppTagChange}
                className="custom-tabs"
              />
            )}
            <div className="flex items-center w-full">
              <div className="flex items-center flex-1 mr-[10px] overflow-x-auto">
                {(systemTags || []).map((tag: any) => (
                  <Tag
                    key={tag.value}
                    color={
                      selectedSystemTags.includes(tag.value)
                        ? 'blue'
                        : 'default'
                    }
                    className="cursor-pointer transition-all duration-200 hover:scale-105 select-none"
                    onClick={() => handleSystemTagClick(tag.value)}
                  >
                    {tag.label}
                  </Tag>
                ))}
              </div>
              <Search
                allowClear
                enterButton
                placeholder={`${t('common.search')}...`}
                className="w-60 flex justify-end"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onSearch={onSearch}
              />
            </div>
          </div>
        }
        {...ifOpenAddModal()}
        onCardClick={(item: CardItem) => navigateToCollectorDetail(item)}
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Collector;
