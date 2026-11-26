import { describe, expect, it } from 'vitest';
import { parseInputs, readPythonFile } from './helpers';

describe('集成调试输入', () => {
  it('保留对象参数并拒绝数组和无效 JSON', () => {
    expect(parseInputs('{"value":2}')).toEqual({ value: 2 });
    expect(() => parseInputs('[]')).toThrow();
    expect(() => parseInputs('bad')).toThrow();
  });
  it('上传 Python 文件，拒绝非 Python 和过大文件', async () => {
    expect(await readPythonFile({ name: 'main.py', size: 40, text: async () => 'def transform(rows, params): return rows' })).toContain('transform');
    await expect(readPythonFile({ name: 'a.exe', size: 4, text: async () => '' })).rejects.toThrow();
    await expect(readPythonFile({ name: 'a.py', size: 100001, text: async () => '' })).rejects.toThrow();
  });
});
