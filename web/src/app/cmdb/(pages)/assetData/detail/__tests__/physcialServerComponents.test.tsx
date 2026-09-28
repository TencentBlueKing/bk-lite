import { describe, expect, it } from 'vitest';
import { BUILD_IN_MODEL } from '@/app/cmdb/constants/asset';
import {
  visibleRelationshipAssociations,
  buildRelationshipMenuSections,
  getDefaultExpandedRelationshipKeys,
} from '../../relationshipMenuData';
import { getAssetColumns } from '@/app/cmdb/utils/common';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

describe('physcial_server Redfish P0 components and fields contract', () => {
  it('includes storage_controller and psu in BUILD_IN_MODEL', () => {
    const modelKeys = BUILD_IN_MODEL.map((m) => m.key);
    expect(modelKeys).toContain('storage_controller');
    expect(modelKeys).toContain('psu');
    expect(modelKeys).toContain('disk');
    expect(modelKeys).toContain('nic');
    expect(modelKeys).toContain('memory');
    expect(modelKeys).toContain('gpu');
  });

  it('renders child associations (storage_controller and psu) in relationships correctly', () => {
    const assoList = [
      {
        model_asst_id: 'physcial_server_contains_storage_controller',
        asst_id: 'contains',
        src_model_id: 'physcial_server',
        dst_model_id: 'storage_controller',
        src_model_name: '物理服务器',
        dst_model_name: '阵列卡',
        inst_list: [
          {
            inst_uuid: 'sc-1',
            inst_name: 'sc-1',
            sc_id: 'RAID.Slot.1-1',
            sc_name: 'PERC H730P',
            sc_vendor: 'Dell',
            sc_model: 'PERC H730P Adapter',
            sc_sn: '123456',
            sc_firmware: '25.5.0.0018',
            health: 'OK',
            self_device: '192.168.1.100',
          },
        ],
      },
      {
        model_asst_id: 'physcial_server_contains_psu',
        asst_id: 'contains',
        src_model_id: 'physcial_server',
        dst_model_id: 'psu',
        src_model_name: '物理服务器',
        dst_model_name: '电源模块',
        inst_list: [
          {
            inst_uuid: 'psu-1',
            inst_name: 'psu-1',
            psu_name: 'PSU1',
            psu_vendor: 'Dell',
            psu_model: 'PWR SPLY,750W',
            psu_sn: 'PSUSN123',
            psu_capacity_watts: 750,
            health: 'OK',
            self_device: '192.168.1.100',
          },
        ],
      },
      {
        model_asst_id: 'physcial_server_contains_disk',
        asst_id: 'contains',
        src_model_id: 'physcial_server',
        dst_model_id: 'disk',
        src_model_name: '物理服务器',
        dst_model_name: '服务器磁盘',
        inst_list: [],
      },
    ];

    const visible = visibleRelationshipAssociations(assoList);
    expect(visible).toHaveLength(2);
    expect(visible.map((v) => v.dst_model_id)).toEqual([
      'storage_controller',
      'psu',
    ]);

    const defaultKeys = getDefaultExpandedRelationshipKeys(assoList);
    expect(defaultKeys).toEqual([
      'physcial_server_contains_storage_controller',
      'physcial_server_contains_psu',
    ]);

    const sections = buildRelationshipMenuSections({
      instances: assoList,
      assoTypes: [{ asst_id: 'contains', asst_name: '包含' }],
      modelId: 'physcial_server',
    });

    expect(sections).toHaveLength(1);
    expect(sections[0].title).toBe('包含');
    expect(sections[0].children).toHaveLength(2);
    expect(sections[0].children.map((c) => c.text)).toEqual(['阵列卡', '电源模块']);
  });

  it('gracefully handles empty child associations without errors', () => {
    const emptyAssoList: any[] = [];
    const visible = visibleRelationshipAssociations(emptyAssoList);
    expect(visible).toEqual([]);

    const sections = buildRelationshipMenuSections({
      instances: emptyAssoList,
      assoTypes: [{ asst_id: 'contains', asst_name: '包含' }],
      modelId: 'physcial_server',
    });
    expect(sections).toEqual([]);
  });

  it('generates asset columns for disk with health and disk_life_percent', () => {
    const diskAttrs: AttrFieldType[] = [
      { attr_id: 'inst_name', attr_name: '实例名', attr_type: 'str', is_required: true, editable: false, option: [] as any },
      { attr_id: 'disk_vendor', attr_name: '磁盘厂商', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'disk', attr_name: '磁盘（GB）', attr_type: 'int', is_required: false, editable: false, option: [] as any },
      { attr_id: 'disk_type', attr_name: '磁盘类型', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'disk_sn', attr_name: '磁盘序列号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'health', attr_name: '健康状态', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'disk_life_percent', attr_name: '寿命百分比', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'self_device', attr_name: '所属设备', attr_type: 'str', is_required: true, editable: false, option: [] as any },
    ];

    const columns = getAssetColumns({ attrList: diskAttrs });
    expect(columns.map((c) => c.dataIndex)).toEqual([
      'inst_name',
      'disk_vendor',
      'disk',
      'disk_type',
      'disk_sn',
      'health',
      'disk_life_percent',
      'self_device',
    ]);
  });

  it('generates asset columns for nic with nic_speed_mbps and nic_iface', () => {
    const nicAttrs: AttrFieldType[] = [
      { attr_id: 'inst_name', attr_name: '实例名', attr_type: 'str', is_required: true, editable: false, option: [] as any },
      { attr_id: 'nic_vendor', attr_name: '厂商', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'nic_model', attr_name: '型号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'nic_iface', attr_name: '接口名', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'nic_mac', attr_name: 'MAC 地址', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'nic_speed_mbps', attr_name: '速率(Mbps)', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'self_device', attr_name: '所属设备', attr_type: 'str', is_required: true, editable: false, option: [] as any },
    ];

    const columns = getAssetColumns({ attrList: nicAttrs });
    expect(columns.map((c) => c.dataIndex)).toEqual([
      'inst_name',
      'nic_vendor',
      'nic_model',
      'nic_iface',
      'nic_mac',
      'nic_speed_mbps',
      'self_device',
    ]);
  });

  it('generates asset columns for storage_controller and psu', () => {
    const scAttrs: AttrFieldType[] = [
      { attr_id: 'sc_id', attr_name: '控制器标识', attr_type: 'str', is_required: true, editable: false, option: [] as any },
      { attr_id: 'sc_name', attr_name: '控制器名称', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'sc_vendor', attr_name: '厂商', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'sc_model', attr_name: '型号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'sc_sn', attr_name: '序列号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'sc_firmware', attr_name: '固件版本', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'health', attr_name: '健康状态', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'self_device', attr_name: '所属设备', attr_type: 'str', is_required: true, editable: false, option: [] as any },
    ];

    const psuAttrs: AttrFieldType[] = [
      { attr_id: 'psu_name', attr_name: '电源名称', attr_type: 'str', is_required: true, editable: false, option: [] as any },
      { attr_id: 'psu_vendor', attr_name: '厂商', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'psu_model', attr_name: '型号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'psu_sn', attr_name: '序列号', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'psu_capacity_watts', attr_name: '额定容量(W)', attr_type: 'int', is_required: false, editable: false, option: [] as any },
      { attr_id: 'health', attr_name: '健康状态', attr_type: 'str', is_required: false, editable: false, option: [] as any },
      { attr_id: 'self_device', attr_name: '所属设备', attr_type: 'str', is_required: true, editable: false, option: [] as any },
    ];

    const scColumns = getAssetColumns({ attrList: scAttrs });
    expect(scColumns.map((c) => c.dataIndex)).toEqual([
      'sc_id',
      'sc_name',
      'sc_vendor',
      'sc_model',
      'sc_sn',
      'sc_firmware',
      'health',
      'self_device',
    ]);

    const psuColumns = getAssetColumns({ attrList: psuAttrs });
    expect(psuColumns.map((c) => c.dataIndex)).toEqual([
      'psu_name',
      'psu_vendor',
      'psu_model',
      'psu_sn',
      'psu_capacity_watts',
      'health',
      'self_device',
    ]);
  });
});
