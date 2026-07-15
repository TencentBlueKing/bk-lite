'use client';
import { useEffect, useState, useRef, useCallback } from 'react';
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
import { useCommon } from '@/app/node-manager/context/common';
import { cloneDeep } from 'lodash';
const { Search } = Input;
const { confirm } = Modal;

const Collector = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCollectorlist, deleteCollector } = useNodeManagerApi();
  const commonContext = useCommon();
  const nodeStateEnum = commonContext?.nodeStateEnum || {};
  const menuItem = useCollectorMenuItem();
  const modalRef = useRef<ModalRef>(null);
  const collectorAbortControllerRef = useRef<AbortController | null>(null);
  const collectorRequestIdRef = useRef<number>(0);
  const [collectorCards, setCollectorCards] = useState<CardItem[]>([]);
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [appTags, setAppTags] = useState<any[]>([]);
  const [osTags, setOsTags] = useState<any[]>([]);
  const [kindTags, setKindTags] = useState<any[]>([]);
  const [selectedAppTag, setSelectedAppTag] = useState<string>('');
  const [selectedOsTags, setSelectedOsTags] = useState<string[]>([]);
  const [selectedSystemTags, setSelectedSystemTags] = useState<string[]>([]);
  const [selectedArchitectureTags, setSelectedArchitectureTags] = useState<
    string[]
  >([]);
  const [tagEnum, setTagEnum] = useState<Record<string, any>>({});

  useEffect(() => {
    if (!isLoading) {
      initData();
    }
  }, [isLoading]);

  // 组件卸载时取消所有请求
  useEffect(() => {
    return () => {
      collectorAbortControllerRef.current?.abort();
    };
  }, []);

  const initData = () => {
    setLoading(true);
    const { apps, tagEnum: newTagEnum } = getTags();
    const defaultAppTag = apps && apps.length > 0 ? apps[0].value : '';
    setSelectedAppTag(defaultAppTag);
    fetchCollectorData({
      searchValue: '',
      appTag: defaultAppTag,
      tagEnum: newTagEnum
    });
  };

  const navigateToCollectorDetail = (item: CardItem) => {
    router.push(`
      /node-manager/collector/detail?id=${item.id}&name=${item.original_name}&displayName=${item.name}&introduction=${item.description}&system=${item.os}&architecture=${item.cpu_architecture || ''}&icon=${item.icon}`);
  };

  const getTags = () => {
    if (nodeStateEnum?.tag) {
      const tagData = nodeStateEnum.tag;
      const apps: any[] = [];
      const osOptions: any[] = [];
      const kindOptions: any[] = [];
      Object.keys(tagData).forEach((key) => {
        const item = tagData[key];
        if (item.is_app) {
          apps.push({ label: item.name, value: key });
        } else if (['linux', 'windows'].includes(key)) {
          osOptions.push({ label: item.name, value: key });
        } else {
          kindOptions.push({ label: item.name, value: key });
        }
      });
      setAppTags(apps);
      setOsTags(osOptions);
      setKindTags(kindOptions);
      setTagEnum(tagData);
      return { apps, osOptions, kindOptions, tagEnum: tagData };
    }
    return { apps: [], osOptions: [], kindOptions: [], tagEnum: {} };
  };

  const architectureTags = [
    { label: 'x86_64', value: 'x86_64' },
    { label: 'ARM64', value: 'arm64' }
  ];

  const handleResult = (res: any, enumMap?: Record<string, any>) => {
    const currentTagEnum = enumMap || tagEnum;
    const tempdata = (res || []).map((item: any) => {
      const tagList = item.tags || [];
      const nonArchitectureTags = tagList.filter(
        (tag: string) => !['x86_64', 'arm64'].includes(tag)
      );
      const displayTags = nonArchitectureTags.map((tag: string) => {
        return currentTagEnum[tag]?.name || (tag === 'arm64' ? 'ARM64' : tag);
      });
      const architectureDisplay =
        item.architecture_display ||
        (item.cpu_architecture === 'arm64'
          ? 'ARM64'
          : item.cpu_architecture || '');
      return {
        ...item,
        name: item.display_name,
        description: item.display_introduction || '--',
        original_name: item.name,
        original_introduction: item.introduction,
        icon: item.icon || 'caijiqizongshu',
        os:
          tagList.find((item: string) => ['linux', 'windows'].includes(item)) ||
          'linux',
        cpu_architecture: item.cpu_architecture,
        tagList: architectureDisplay
          ? [...displayTags, architectureDisplay]
          : displayTags,
        originalTags: tagList
      };
    });
    setCollectorCards(tempdata);
  };

  const buildSelectedTags = ({
    appTag = selectedAppTag,
    osTags = [],
    kindTags = selectedSystemTags,
    architectureTags = selectedArchitectureTags
  }: {
    appTag?: string;
    osTags?: string[];
    kindTags?: string[];
    architectureTags?: string[];
  }) => {
    return [appTag, ...osTags, ...kindTags, ...architectureTags].filter(
      Boolean
    );
  };

  const fetchCollectorData = async ({
    searchValue = search,
    appTag = selectedAppTag,
    osTags = selectedOsTags,
    sysTags = selectedSystemTags,
    architectureValues = selectedArchitectureTags,
    tagEnum: enumMap
  }: {
    searchValue?: string;
    appTag?: string;
    osTags?: string[];
    sysTags?: string[];
    architectureValues?: string[];
    tagEnum?: Record<string, any>;
  } = {}) => {
    // 取消上一次请求
    collectorAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    collectorAbortControllerRef.current = abortController;
    const currentRequestId = ++collectorRequestIdRef.current;
    const requestParams: any = { name: searchValue };
    const tagsArray = buildSelectedTags({
      appTag,
      osTags,
      kindTags: sysTags,
      architectureTags: architectureValues
    });
    if (tagsArray.length > 0) {
      requestParams.tags = tagsArray.join(',');
    }
    try {
      setLoading(true);
      const res = await getCollectorlist(requestParams, {
        signal: abortController.signal
      });
      // 只有最新请求才处理数据
      if (currentRequestId !== collectorRequestIdRef.current) return;
      handleResult(res, enumMap);
    } finally {
      // 只有最新请求才控制 loading
      if (currentRequestId === collectorRequestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const openModal = (config: any) => {
    const form = cloneDeep(config?.form || {});
    if (config?.type === 'edit') {
      form.name = form.original_name;
      form.description = form.original_introduction;
    }
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form,
      key: config?.key,
      appTag: selectedAppTag
    });
  };

  const handleSubmit = (type?: string) => {
    if (type === 'upload') return;
    fetchCollectorData({ searchValue: search });
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
            fetchCollectorData({ searchValue: search });
          } finally {
            return resolve(true);
          }
        });
      }
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

  const handleOsTagClick = (tag: string) => {
    const newSelectedTags = selectedOsTags.includes(tag)
      ? selectedOsTags.filter((t: string) => t !== tag)
      : [...selectedOsTags, tag];
    setSelectedOsTags(newSelectedTags);
    fetchCollectorData({
      searchValue: search,
      appTag: selectedAppTag,
      osTags: newSelectedTags,
      sysTags: selectedSystemTags
    });
  };

  const handleSystemTagClick = (tag: string) => {
    const newSelectedTags = selectedSystemTags.includes(tag)
      ? selectedSystemTags.filter((t: string) => t !== tag)
      : [...selectedSystemTags, tag];
    setSelectedSystemTags(newSelectedTags);
    fetchCollectorData({
      searchValue: search,
      appTag: selectedAppTag,
      osTags: selectedOsTags,
      sysTags: newSelectedTags
    });
  };

  const handleAppTagChange = (value: string | number) => {
    const newAppTag = value as string;
    setSelectedAppTag(newAppTag);
    fetchCollectorData({
      searchValue: search,
      appTag: newAppTag,
      osTags: selectedOsTags,
      sysTags: selectedSystemTags,
      architectureValues: selectedArchitectureTags
    });
  };

  const handleArchitectureTagClick = (tag: string) => {
    const newSelectedTags = selectedArchitectureTags.includes(tag)
      ? selectedArchitectureTags.filter((item) => item !== tag)
      : [...selectedArchitectureTags, tag];
    setSelectedArchitectureTags(newSelectedTags);
    fetchCollectorData({
      searchValue: search,
      appTag: selectedAppTag,
      osTags: selectedOsTags,
      sysTags: selectedSystemTags,
      architectureValues: newSelectedTags
    });
  };

  const ifOpenAddModal = () => {
    return {
      openModal: () =>
        openModal({
          title: t('node-manager.collector.addCollector'),
          type: 'add',
          form: {}
        })
    };
  };

  const onSearch = (searchValue: string) => {
    setSearch(searchValue);
    fetchCollectorData({ searchValue });
  };

  return (
    <div className="h-[calc(100vh-88px)] w-full">
      <EntityList
        data={collectorCards}
        loading={loading}
        menuActions={(value) => menuActions(value)}
        filter={false}
        search={false}
        toolbarPrefix={
          <div className="flex flex-col gap-2">
            {appTags.length > 0 && (
              <Segmented
                options={appTags}
                value={selectedAppTag}
                onChange={handleAppTagChange}
                className="custom-tabs"
              />
            )}
            <div className="flex flex-wrap items-center gap-1.5">
              {(osTags || []).map((tag: any) => (
                <Tag
                  key={tag.value}
                  color={
                    selectedOsTags.includes(tag.value) ? 'blue' : 'default'
                  }
                  className="cursor-pointer transition-all duration-200 hover:scale-105 select-none"
                  onClick={() => handleOsTagClick(tag.value)}
                >
                  {tag.label}
                </Tag>
              ))}
              {(kindTags || []).map((tag: any) => (
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
              {architectureTags.map((tag) => (
                <Tag
                  key={tag.value}
                  color={
                    selectedArchitectureTags.includes(tag.value)
                      ? 'blue'
                      : 'default'
                  }
                  className="cursor-pointer transition-all duration-200 hover:scale-105 select-none"
                  onClick={() => handleArchitectureTagClick(tag.value)}
                >
                  {tag.label}
                </Tag>
              ))}
            </div>
          </div>
        }
        operateSection={
          <Search
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            className="w-60"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={onSearch}
          />
        }
        {...ifOpenAddModal()}
        onCardClick={(item: CardItem) => navigateToCollectorDetail(item)}
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Collector;
