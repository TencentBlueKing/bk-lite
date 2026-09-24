import { afterEach, describe, expect, it } from 'vitest';

import { createPageContextRegistry } from '../registry';
import { overlaySection, readOverlayBlocks } from '../domSnapshot';
import { PAGE_OVERLAY_SECTION_ID } from '../domSnapshot';

describe('overlay snapshot (modal / drawer)', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('reads open modal title and control values', () => {
    document.body.innerHTML = `
      <div class="ant-modal-wrap" style="display: block">
        <div class="ant-modal">
          <div class="ant-modal-content">
            <div class="ant-modal-header">
              <div class="ant-modal-title">展示指标配置 - 主机</div>
            </div>
            <div class="ant-modal-body">
              <input class="ant-input" value="CPU使用率" placeholder="列名" />
              <input class="ant-input" value="cpu" placeholder="变量 ID, 如 vm_ip" />
              <div class="ant-select">
                <span class="ant-select-selection-item">主机 (Telegraf)</span>
              </div>
              <div class="ant-select">
                <span class="ant-select-selection-item">CPU使用率</span>
              </div>
              <input type="password" class="ant-input" value="secret-token" />
            </div>
          </div>
        </div>
      </div>
    `;
    const blocks = readOverlayBlocks();
    expect(blocks[0]).toContain('[弹窗] 展示指标配置 - 主机');
    expect(blocks[0]).toContain('CPU使用率');
    expect(blocks[0]).toContain('主机 (Telegraf)');
    expect(blocks[0]).toContain('变量 ID, 如 vm_ip: cpu');
    expect(blocks[0]).not.toContain('secret-token');
  });

  it('ignores closed modal wraps and captures open drawers', () => {
    document.body.innerHTML = `
      <div class="ant-modal-wrap" style="display: none">
        <div class="ant-modal">
          <div class="ant-modal-title">已关闭</div>
          <div class="ant-modal-body">不应出现</div>
        </div>
      </div>
      <div class="ant-drawer ant-drawer-open">
        <div class="ant-drawer-content-wrapper">
          <div class="ant-drawer-content">
            <div class="ant-drawer-header"><div class="ant-drawer-title">模板配置</div></div>
            <div class="ant-drawer-body">
              <div class="ant-form-item">
                <label>采集间隔</label>
                <input class="ant-input" value="60s" />
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    const section = overlaySection()[0];
    expect(section.id).toBe(PAGE_OVERLAY_SECTION_ID);
    expect(section.content).toContain('[侧边栏] 模板配置');
    expect(section.content).toContain('60s');
    expect(section.content).not.toContain('已关闭');
    expect(section.content).not.toContain('不应出现');
  });

  it('merges live overlay on collect even when pilot cache is warm', async () => {
    document.body.innerHTML = '';
    const registry = createPageContextRegistry({
      getPathname: () => '/monitor/integration/object',
      pilots: [{
        test: () => true,
        load: async () => ({
          getMessage: () => ({ title: 'monitor-object:主机', currentTime: 'stable' }),
          getContext: async () => ({
            title: '对象',
            sections: [{ id: 'list', label: '列表', content: '主机行', priority: 4 }],
          }),
        }),
      }],
    });

    const first = await registry.collect();
    expect(first?.sections?.some((section) => section.id === PAGE_OVERLAY_SECTION_ID)).toBe(false);

    document.body.innerHTML = `
      <div class="ant-modal-wrap" style="display: block">
        <div class="ant-modal">
          <div class="ant-modal-title">展示指标配置 - 主机</div>
          <div class="ant-modal-body">
            <input class="ant-input" value="内存使用率" />
          </div>
        </div>
      </div>
    `;
    const second = await registry.collect();
    const overlay = second?.sections?.find((section) => section.id === PAGE_OVERLAY_SECTION_ID);
    expect(overlay?.content).toContain('展示指标配置 - 主机');
    expect(overlay?.content).toContain('内存使用率');
    expect(second?.sections?.some((section) => section.content.includes('主机行'))).toBe(true);
  });
});
