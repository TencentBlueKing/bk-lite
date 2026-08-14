import type { WebChatConfig } from '@webchat/core';

const MEBIBYTE = 1024 * 1024;

export interface ImageBudget {
  allowUnknownImagePreview: boolean;
  imageReadConcurrency: number;
  maxImageCount: number;
  maxImagePixels: number;
  maxTotalImageBytes: number;
  maxTotalImagePixels: number;
}

export interface ImageFile {
  name: string;
  size: number;
  type: string;
}

export interface PendingImage {
  dataUrl: string;
  height: number | null;
  name: string;
  pixels: number | null;
  previewable: boolean;
  size: number;
  width: number | null;
}

export interface ImageDimensions {
  height: number;
  pixels: number;
  width: number;
}

export interface InspectedImageFile<T extends ImageFile = ImageFile> {
  file: T;
  height: number | null;
  pixels: number | null;
  width: number | null;
}

export type ImageBudgetViolation =
  { limit: number; ok: false; reason: 'count' | 'bytes' | 'image-pixels' | 'total-pixels' };

export type PendingImageAction =
  | { images: readonly PendingImage[]; type: 'append' }
  | { index: number; type: 'remove' }
  | { type: 'clear' };

export const DEFAULT_IMAGE_BUDGET: Readonly<ImageBudget> = {
  allowUnknownImagePreview: false,
  imageReadConcurrency: 2,
  maxImageCount: 4,
  maxImagePixels: 16 * MEBIBYTE,
  maxTotalImageBytes: 16 * MEBIBYTE,
  maxTotalImagePixels: 32 * MEBIBYTE,
};

const positiveIntegerOr = (value: number | undefined, fallback: number): number =>
  Number.isSafeInteger(value) && (value ?? 0) > 0 ? (value as number) : fallback;

/** Resolves optional public configuration to safe positive image budget limits. */
export const resolveImageBudget = (
  config: Partial<
    Pick<
      WebChatConfig,
      | 'allowUnknownImagePreview'
      | 'imageReadConcurrency'
      | 'maxImageCount'
      | 'maxImagePixels'
      | 'maxTotalImageBytes'
      | 'maxTotalImagePixels'
    >
  >
): ImageBudget => ({
  allowUnknownImagePreview: config.allowUnknownImagePreview === true,
  imageReadConcurrency: positiveIntegerOr(
    config.imageReadConcurrency,
    DEFAULT_IMAGE_BUDGET.imageReadConcurrency
  ),
  maxImageCount: positiveIntegerOr(config.maxImageCount, DEFAULT_IMAGE_BUDGET.maxImageCount),
  maxImagePixels: positiveIntegerOr(config.maxImagePixels, DEFAULT_IMAGE_BUDGET.maxImagePixels),
  maxTotalImageBytes: positiveIntegerOr(
    config.maxTotalImageBytes,
    DEFAULT_IMAGE_BUDGET.maxTotalImageBytes
  ),
  maxTotalImagePixels: positiveIntegerOr(
    config.maxTotalImagePixels,
    DEFAULT_IMAGE_BUDGET.maxTotalImagePixels
  ),
});

/** Returns the original byte total represented by selected or pending images. */
export const pendingImageBytes = (images: readonly Pick<ImageFile, 'size'>[]): number =>
  images.reduce((total, image) => total + image.size, 0);

/** Returns the known decoded-pixel total represented by pending images. */
export const pendingImagePixels = (images: readonly Pick<PendingImage, 'pixels'>[]): number =>
  images.reduce((total, image) => total + (image.pixels ?? 0), 0);

const hasBytes = (bytes: Uint8Array, offset: number, expected: readonly number[]): boolean =>
  expected.every((value, index) => bytes[offset + index] === value);

const containsBytes = (bytes: Uint8Array, expected: readonly number[]): boolean => {
  for (let offset = 0; offset <= bytes.length - expected.length; offset += 1) {
    if (hasBytes(bytes, offset, expected)) return true;
  }
  return false;
};

const dimensions = (width: number, height: number): ImageDimensions | null => {
  const pixels = width * height;
  return Number.isSafeInteger(width) && Number.isSafeInteger(height) && width > 0 && height > 0 &&
    Number.isSafeInteger(pixels)
    ? { height, pixels, width }
    : null;
};

/** Parses dimensions from common raster headers without asking the browser to decode image pixels. */
export const parseImageDimensions = (input: ArrayBuffer | Uint8Array): ImageDimensions | null => {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  if (bytes.length >= 24 && hasBytes(bytes, 0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
    if (containsBytes(bytes, [0x61, 0x63, 0x54, 0x4c])) return null;
    return dimensions(view.getUint32(16), view.getUint32(20));
  }
  if (bytes.length >= 26 && hasBytes(bytes, 0, [0x42, 0x4d])) {
    return dimensions(Math.abs(view.getInt32(18, true)), Math.abs(view.getInt32(22, true)));
  }
  if (bytes.length >= 4 && hasBytes(bytes, 0, [0xff, 0xd8])) {
    let offset = 2;
    while (offset + 8 < bytes.length) {
      while (bytes[offset] === 0xff) offset += 1;
      const marker = bytes[offset];
      offset += 1;
      if (marker === 0xd8 || marker === 0xd9) continue;
      if (offset + 2 > bytes.length) return null;
      const length = view.getUint16(offset);
      const isStartOfFrame = (marker >= 0xc0 && marker <= 0xc3) ||
        (marker >= 0xc5 && marker <= 0xc7) || (marker >= 0xc9 && marker <= 0xcb) ||
        (marker >= 0xcd && marker <= 0xcf);
      if (isStartOfFrame && length >= 7 && offset + 7 <= bytes.length) {
        return dimensions(view.getUint16(offset + 5), view.getUint16(offset + 3));
      }
      if (length < 2 || offset + length > bytes.length) return null;
      offset += length;
    }
  }
  return null;
};

/** Reads bounded file bytes and inspects image dimensions before Data URL decoding starts. */
export const inspectImageBatch = async <T extends ImageFile & { arrayBuffer(): Promise<ArrayBuffer> }>(
  files: readonly T[],
  concurrency: number,
  signal?: AbortSignal
): Promise<InspectedImageFile<T>[]> => {
  const results = new Array<InspectedImageFile<T>>(files.length);
  let nextIndex = 0;
  let firstError: unknown;
  const workerCount = Math.min(positiveIntegerOr(concurrency, 1), files.length);
  const worker = async () => {
    while (!signal?.aborted && firstError === undefined && nextIndex < files.length) {
      const index = nextIndex;
      nextIndex += 1;
      try {
        const file = files[index];
        const parsed = parseImageDimensions(await file.arrayBuffer());
        results[index] = {
          file,
          height: parsed?.height ?? null,
          pixels: parsed?.pixels ?? null,
          width: parsed?.width ?? null,
        };
      } catch (error) {
        firstError ??= error;
      }
    }
  };
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (signal?.aborted) throw new Error('图片尺寸读取已取消。');
  if (firstError !== undefined) throw firstError;
  return results;
};

/** Validates decoded dimensions and the estimated RGBA memory budget before browser decode. */
export const validateImagePixelBudget = (
  current: readonly Pick<PendingImage, 'pixels'>[],
  incoming: readonly InspectedImageFile[],
  budget: ImageBudget
): { ok: true } | ImageBudgetViolation => {
  if (incoming.some(({ pixels }) => pixels !== null && pixels > budget.maxImagePixels)) {
    return { limit: budget.maxImagePixels, ok: false, reason: 'image-pixels' };
  }
  const incomingPixels = incoming.reduce((total, image) => total + (image.pixels ?? 0), 0);
  if (pendingImagePixels(current) + incomingPixels > budget.maxTotalImagePixels) {
    return { limit: budget.maxTotalImagePixels, ok: false, reason: 'total-pixels' };
  }
  return { ok: true };
};

/** Validates an incoming batch atomically against the current message budget. */
export const validateImageBatch = (
  current: readonly Pick<ImageFile, 'size'>[],
  incoming: readonly ImageFile[],
  budget: ImageBudget
): { ok: true } | ImageBudgetViolation => {
  if (current.length + incoming.length > budget.maxImageCount) {
    return { limit: budget.maxImageCount, ok: false, reason: 'count' };
  }

  const incomingBytes = incoming.reduce((total, file) => total + file.size, 0);
  if (pendingImageBytes(current) + incomingBytes > budget.maxTotalImageBytes) {
    return { limit: budget.maxTotalImageBytes, ok: false, reason: 'bytes' };
  }

  return { ok: true };
};

/** Reads one browser File as a Data URL and propagates read or abort failures. */
export const readFileAsDataUrl = (file: File, signal?: AbortSignal): Promise<string> =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    const cleanup = () => signal?.removeEventListener('abort', abort);
    const abort = () => reader.abort();
    reader.onload = (event) => {
      cleanup();
      resolve(event.target?.result as string);
    };
    reader.onerror = () => {
      cleanup();
      reject(reader.error || new Error(`读取图片“${file.name}”失败。`));
    };
    reader.onabort = () => {
      cleanup();
      reject(new Error(`读取图片“${file.name}”已取消。`));
    };
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort', abort, { once: true });
    reader.readAsDataURL(file);
  });

/** Reads a batch with bounded concurrency while preserving the input order. */
export const readImageBatch = async <T extends ImageFile>(
  files: readonly (T | InspectedImageFile<T>)[],
  concurrency: number,
  readFile: (file: T, signal?: AbortSignal) => Promise<string>,
  signal?: AbortSignal
): Promise<PendingImage[]> => {
  if (files.length === 0) return [];

  const results = new Array<PendingImage>(files.length);
  let nextIndex = 0;
  let firstError: unknown;
  const workerCount = Math.min(positiveIntegerOr(concurrency, 1), files.length);

  const worker = async () => {
    while (!signal?.aborted && firstError === undefined && nextIndex < files.length) {
      const index = nextIndex;
      nextIndex += 1;
      const input = files[index];
      const file = 'file' in input ? input.file : input;
      try {
        const dataUrl = await readFile(file, signal);
        results[index] = {
          dataUrl,
          height: 'file' in input ? input.height : null,
          name: file.name,
          pixels: 'file' in input ? input.pixels : null,
          previewable: 'file' in input && input.pixels !== null,
          size: file.size,
          width: 'file' in input ? input.width : null,
        };
      } catch (error) {
        firstError ??= error;
      }
    }
  };

  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (signal?.aborted) throw new Error('图片读取已取消。');
  if (firstError !== undefined) throw firstError;
  return results;
};

/** Applies append, remove, and clear operations to the pending image ledger. */
export const pendingImagesReducer = (
  state: readonly PendingImage[],
  action: PendingImageAction
): PendingImage[] => {
  switch (action.type) {
    case 'append':
      return [...state, ...action.images];
    case 'remove':
      return state.filter((_, index) => index !== action.index);
    case 'clear':
      return [];
  }
};
