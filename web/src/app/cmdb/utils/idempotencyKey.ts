interface IdempotencyCrypto {
  randomUUID?: () => string;
  getRandomValues?: (values: Uint8Array) => Uint8Array;
}

/** 幂等键。HTTP 内网页不是安全上下文，浏览器不提供 randomUUID，这时改用 getRandomValues。 */
export const createIdempotencyKey = (
  cryptoApi: IdempotencyCrypto | undefined = globalThis.crypto,
): string => {
  if (typeof cryptoApi?.randomUUID === 'function') {
    return cryptoApi.randomUUID();
  }

  const values = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === 'function') {
    cryptoApi.getRandomValues(values);
  } else {
    for (let index = 0; index < values.length; index += 1) {
      values[index] = Math.floor(Math.random() * 256);
    }
  }
  values[6] = (values[6] & 0x0f) | 0x40;
  values[8] = (values[8] & 0x3f) | 0x80;
  const hex = Array.from(values, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};
