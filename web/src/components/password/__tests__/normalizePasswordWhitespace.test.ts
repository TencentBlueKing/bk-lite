import { describe, expect, it } from 'vitest';
import {
  normalizePasswordFields,
  normalizePasswordWhitespace,
} from '../normalizePasswordWhitespace';

describe('normalizePasswordWhitespace', () => {
  it('只移除首尾空白并保留中间空格', () => {
    expect(normalizePasswordWhitespace(' \tpass word\n ')).toEqual({
      value: 'pass word',
      changed: true,
    });
  });

  it('无首尾空白时保持原值', () => {
    expect(normalizePasswordWhitespace('pass word')).toEqual({
      value: 'pass word',
      changed: false,
    });
  });

  it('按字段元数据规范化密码并默认跳过只读字段', () => {
    const values = {
      username: ' admin ',
      password: ' secret ',
      readonlySecret: ' keep-spaces ',
    };
    const result = normalizePasswordFields(values, [
      { name: 'username', type: 'input' },
      { name: 'password', type: 'password' },
      { name: 'readonlySecret', type: 'password', editable: false },
    ]);

    expect(result.values).toEqual({
      username: ' admin ',
      password: 'secret',
      readonlySecret: ' keep-spaces ',
    });
    expect(result.changedFields).toEqual(['password']);
    expect(values.password).toBe(' secret ');
  });

  it('创建态可以显式包含 editable=false 的密码字段', () => {
    const result = normalizePasswordFields(
      { password: ' secret ' },
      [{ name: 'password', type: 'password', editable: false }],
      { includeReadOnly: true },
    );

    expect(result.values.password).toBe('secret');
    expect(result.changedFields).toEqual(['password']);
  });
});
