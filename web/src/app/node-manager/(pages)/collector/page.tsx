'use client';
import { useEffect, useState, useRef } from 'react';
import { Input, Button, message, Modal, Tag, Segmented, Tooltip } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import useNodeManagerApi from '@/app/node-manager/api';
import EntityList from '@/components/entity-list/index';
import GridEntityCard from '@/components/grid-entity-card';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import SourceOriginBadge from '@/components/source-origin-badge';
import Icon from '@/components/icon';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import type { CardItem, CardTag } from '@/app/node-manager/types';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import CollectorReleaseImportModal from '@/app/node-manager/components/collectorReleaseImportModal';
import { ModalRef } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';
import { useCollectorMenuItem } from '@/app/node-manager/hooks/collector';
import { useCommon } from '@/app/node-manager/context/common';
import { buildCollectorPackStatusTag } from '@/app/node-manager/utils/collectorConfig';
import { buildCollectNeedUpdateAssetUrl } from '@/app/monitor/utils/collectNeedUpdate';
import { cloneDeep } from 'lodash';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
const { Search } = Input;
const { confirm } = Modal;

type CollectorCard = CardItem & {
  is_pre?: boolean;
  is_build_in?: boolean;
};

function collectorOrigin(item: CollectorCard) {
  if (typeof item.is_pre === 'boolean') {
    return item.is_pre ? 'builtin' : 'external';
  }
  if (typeof item.is_build_in === 'boolean') {
    return item.is_build_in ? 'builtin' : 'external';
  }
  return undefined;
}

function collectorCardMeta(item: CollectorCard) {
  const origin = collectorOrigin(item);
  const labels: string[] = [];
  const statusTags: Array<{ name: string; color?: string; tooltip?: string }> = [];
  (item.tagList || []).forEach((tag: CardTag) => {
    if (typeof tag === 'object' && tag?.name) {
      statusTags.push(tag);
    } else if (tag) {
      labels.push(String(tag));
    }
  });
  return (
    <>
      {origin ? (
        <SourceOriginBadge
          kind={origin}
          className="h-5 px-1.5 text-[11px] leading-5"
        />
      ) : null}
      {labels.map((label) => (
        <span
          key={label}
          className="inline-flex h-5 items-center rounded-md bg-[var(--color-fill-1)] px-1.5 text-[11px] font-normal text-[var(--color-text-3)]"
        >
          {label}
        </span>
      ))}
      {statusTags.map((tag, idx) => (
        <Tooltip key={`${tag.name}-${idx}`} title={tag.tooltip}>
          <Tag color={tag.color} className="mr-0">
            {tag.name}
          </Tag>
        </Tooltip>
      ))}
    </>
  );
}

const Collector = () => {
  const router = useScreenAwareRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getCollectorlist, deleteCollector, restoreCollectorRelease } =
    useNodeManagerApi();
  const commonContext = useCommon();
  const nodeStateEnum = commonContext?.nodeStateEnum || {};
  const menuItem = useCollectorMenuItem();
  const modalRef = useRef<ModalRef>(null);
  const collectorAbortControllerRef = useRef<AbortController | null>(null);
  const collectorRequestIdRef = useRef<number>(0);
  const [collectorCards, setCollectorCards] = useState<CardItem[]>([]);
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [importOpen, setImportOpen] = useState(false);
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
      const packStatusTag = buildCollectorPackStatusTag(
        item.latest_package_version,
        t,
        {
          pinnedVersion: item.imported_package_version || item.pack_version
        }
      );
      const extraTags = [packStatusTag, ...(item.covered_architectures || [])];
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
        latest_package_version: item.latest_package_version,
        covered_architectures: item.covered_architectures || [],
        pack_version: item.pack_version || '',
        tagList: architectureDisplay
          ? [...displayTags, architectureDisplay, ...extraTags]
          : [...displayTags, ...extraTags],
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
      if (currentRequestId !== collectorRequestIdRef.current) return;
      handleResult(res, enumMap);
    } finally {
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

  const handleRestoreBuiltin = (collectorName: string) => {
    confirm({
      title: t('node-manager.packetManage.restoreBuiltin'),
      content: t('node-manager.packetManage.restoreBuiltinConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk() {
        return restoreCollectorRelease(collectorName).then((result: any) => {
          fetchCollectorData({ searchValue: search });
          const staleCount = Number(result?.stale_instance_count) || 0;
          if (staleCount > 0) {
            Modal.success({
              title: t('node-manager.packetManage.restoreSuccess'),
              content: t('node-manager.packetManage.restoreBuiltinStaleHint', '', {
                count: staleCount
              }),
              okText: t('node-manager.packetManage.goToStaleAssets'),
              onOk: () => {
                router.push(
                  buildCollectNeedUpdateAssetUrl({
                    monitorObjectId: result?.monitor_object_id,
                    pluginId: result?.plugin_id,
                    needUpdate: true
                  })
                );
              }
            });
            return;
          }
          message.success(t('node-manager.packetManage.restoreSuccess'));
        });
      }
    });
  };

  const buildCollectorMenuItems = (data: any): MoreActionsDropdownItem[] => {
    const items: MoreActionsDropdownItem[] = menuItem.map((item) => ({
      key: item.key,
      label: item.title,
      permission: item.role,
      onClick: () =>
        openModal({ ...item.config, form: data, key: 'collector' }),
    }));
    items.push({
      key: 'delete',
      label: t('common.delete'),
      permission: 'Delete',
      danger: true,
      confirm: {
        title: t('common.delete'),
        content: t('node-manager.packetManage.deleteInfo'),
      },
      onClick: async () => {
        await deleteCollector({ id: data.id });
        message.success(t('common.successfullyDeleted'));
        fetchCollectorData({ searchValue: search });
      },
    });
    if (data.pack_version) {
      items.push({
        key: 'restore',
        label: t('node-manager.packetManage.restoreBuiltin'),
        permission: 'AddPacket',
        onClick: () => handleRestoreBuiltin(data.original_name),
      });
    }
    return items;
  };

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

  const onSearch = (searchValue: string) => {
    setSearch(searchValue);
    fetchCollectorData({ searchValue });
  };

  return (
    <div className="h-[calc(100vh-88px)] w-full">
      <EntityList
        data={collectorCards}
        loading={loading}
        filter={false}
        search={false}
        loadingContent={<CardGridSkeleton count={8} />}
        renderCard={(item: CollectorCard) => (
          <GridEntityCard
            name={item.name}
            description={item.description}
            icon={<Icon type={item.icon} className="text-2xl" />}
            meta={collectorCardMeta(item)}
            menuItems={buildCollectorMenuItems(item)}
            onClick={() => navigateToCollectorDetail(item)}
          />
        )}
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
          <div className="flex items-center gap-2">
            <Search
              allowClear
              enterButton
              placeholder={`${t('common.search')}...`}
              className="w-60"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={onSearch}
            />
            <PermissionWrapper requiredPermissions={['AddPacket']}>
              <Button type="primary" onClick={() => setImportOpen(true)}>
                {t('node-manager.packetManage.importPack')}
              </Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() =>
                  openModal({
                    title: t('node-manager.collector.addCollector'),
                    type: 'add',
                    form: {},
                  })
                }
              >
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          </div>
        }
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
      <CollectorReleaseImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={() => fetchCollectorData({ searchValue: search })}
      />
    </div>
  );
};

export default Collector;
