// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { downloadPluginConfig } from '../exportDownload';

describe('downloadPluginConfig', () => {
  const createObjectURL = vi.fn<(blob: Blob | MediaSource) => string>();
  const revokeObjectURL = vi.fn<(url: string) => void>();

  beforeEach(() => {
    createObjectURL.mockReturnValue('blob:plugin-config');
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
  });

  afterEach(() => {
    document.body.replaceChildren();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('下载配置后移除链接并释放 Object URL', () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const blob = new Blob(['config']);

    downloadPluginConfig(blob, 'plugin.json');

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
    expect(document.body.querySelector('a')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:plugin-config');
  });

  it('点击下载抛错时仍移除链接并释放 Object URL', () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
      throw new Error('download blocked');
    });

    expect(() => downloadPluginConfig(new Blob(['config']), 'plugin.json'))
      .toThrow('download blocked');
    expect(document.body.querySelector('a')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });

  it('链接挂载抛错时仍释放 Object URL', () => {
    vi.spyOn(document.body, 'appendChild').mockImplementation(() => {
      throw new Error('append blocked');
    });

    expect(() => downloadPluginConfig(new Blob(['config']), 'plugin.json'))
      .toThrow('append blocked');
    expect(document.body.querySelector('a')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });

  it('链接属性赋值抛错时仍释放 Object URL', () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'href', 'set').mockImplementation(() => {
      throw new Error('href blocked');
    });

    expect(() => downloadPluginConfig(new Blob(['config']), 'plugin.json'))
      .toThrow('href blocked');
    expect(document.body.querySelector('a')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });

  it('链接 remove 抛错时回退移除节点并释放 Object URL', () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      vi.spyOn(this, 'remove').mockImplementation(() => {
        throw new Error('remove blocked');
      });
    });

    expect(() => downloadPluginConfig(new Blob(['config']), 'plugin.json'))
      .toThrow('remove blocked');
    expect(document.body.querySelector('a')).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });
});
