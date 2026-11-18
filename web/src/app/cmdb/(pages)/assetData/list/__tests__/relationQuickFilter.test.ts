import { quickFilterSlots, relationFilterPayload } from '../relationQuickFilter';

const edges = [
  { model_asst_id: 'rack_contains_switch', src_model_id: 'rack', dst_model_id: 'switch', mapping: '1:n', quick_filter: true },
  { model_asst_id: 'server_room_run_rack', src_model_id: 'server_room', dst_model_id: 'rack', mapping: '1:n', quick_filter: true },
  { model_asst_id: 'application_run_host', src_model_id: 'application', dst_model_id: 'host', mapping: 'n:n', quick_filter: true },
  { model_asst_id: 'qcloud_cvm_belong_qcloud', src_model_id: 'qcloud_cvm', dst_model_id: 'qcloud', mapping: 'n:1', quick_filter: true },
  { model_asst_id: 'host_run_mysql', src_model_id: 'host', dst_model_id: 'mysql', mapping: '1:n', quick_filter: false },
];

const nameOf = (modelId: string) => ({ rack: '机柜', server_room: '机房', application: '应用', qcloud: '腾讯云' }[modelId] || modelId);

describe('关联快捷筛选槽位', () => {
  it('设备页选机柜，机柜页选机房，主机页选应用，云对象页选云平台', () => {
    expect(quickFilterSlots('switch', edges, nameOf)).toEqual([
      { modelAsstId: 'rack_contains_switch', targetModelId: 'rack', labelName: '机柜' },
    ]);
    expect(quickFilterSlots('rack', edges, nameOf)).toEqual([
      { modelAsstId: 'server_room_run_rack', targetModelId: 'server_room', labelName: '机房' },
    ]);
    expect(quickFilterSlots('host', edges, nameOf)).toEqual([
      { modelAsstId: 'application_run_host', targetModelId: 'application', labelName: '应用' },
    ]);
    expect(quickFilterSlots('qcloud_cvm', edges, nameOf)).toEqual([
      { modelAsstId: 'qcloud_cvm_belong_qcloud', targetModelId: 'qcloud', labelName: '腾讯云' },
    ]);
  });

  it('同一个对端只出现一个下拉', () => {
    const duplicated = [
      edges[3],
      { ...edges[3], model_asst_id: 'qcloud_cvm_belong_qcloud_copy' },
    ];
    expect(quickFilterSlots('qcloud_cvm', duplicated, nameOf)).toEqual([
      { modelAsstId: 'qcloud_cvm_belong_qcloud', targetModelId: 'qcloud', labelName: '腾讯云' },
    ]);
  });

  it('关闭的关联不出现，同一模型最多两个', () => {
    const many = ['server_room', 'datacenter', 'building'].map((src) => ({
      model_asst_id: `${src}_run_rack`,
      src_model_id: src,
      dst_model_id: 'rack',
      mapping: '1:n',
      quick_filter: true,
    }));
    expect(quickFilterSlots('rack', many, nameOf)).toHaveLength(2);
    expect(quickFilterSlots('host', edges, nameOf).some((item) => item.modelAsstId === 'host_run_mysql')).toBe(false);
  });

  it('只提交选了值的关联', () => {
    expect(relationFilterPayload({ rack_contains_switch: ['a'], server_room_run_rack: [] })).toEqual([
      { model_asst_id: 'rack_contains_switch', inst_uuids: ['a'] },
    ]);
  });
});
