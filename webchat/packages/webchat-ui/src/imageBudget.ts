import type { WebChatConfig } from '@webchat/core';

const MEBIBYTE = 1024 * 1024;

export interface ImageBudget {
  imageReadConcurrency: number;
  maxImageCount: number;
  maxTotalImageBytes: number;
}

export interface ImageFile {
  name: string;
  size: number;
  type: string;
}

export interface PendingImage {
  dataUrl: string;
  name: string;
  size: number;
}

export type ImageBudgetViolation =
  { limit: number; ok: false; reason: 'count' } | { limit: number; ok: false; reason: 'bytes' };

export type PendingImageAction =
  | { images: readonly PendingImage[]; type: 'append' }
  | { index: number; type: 'remove' }
  | { type: 'clear' };

export const DEFAULT_IMAGE_BUDGET: Readonly<ImageBudget> = {
  imageReadConcurrency: 2,
  maxImageCount: 4,
  maxTotalImageBytes: 16 * MEBIBYTE,
};

const positiveIntegerOr = (value: number | undefined, fallback: number): number =>
  Number.isSafeInteger(value) && (value ?? 0) > 0 ? (value as number) : fallback;

export const resolveImageBudget = (
  config: Partial<
    Pick<WebChatConfig, 'imageReadConcurrency' | 'maxImageCount' | 'maxTotalImageBytes'>
  >
): ImageBudget => ({
  imageReadConcurrency: positiveIntegerOr(
    config.imageReadConcurrency,
    DEFAULT_IMAGE_BUDGET.imageReadConcurrency
  ),
  maxImageCount: positiveIntegerOr(config.maxImageCount, DEFAULT_IMAGE_BUDGET.maxImageCount),
  maxTotalImageBytes: positiveIntegerOr(
    config.maxTotalImageBytes,
    DEFAULT_IMAGE_BUDGET.maxTotalImageBytes
  ),
});

export const pendingImageBytes = (images: readonly PendingImage[]): number =>
  images.reduce((total, image) => total + image.size, 0);

export const validateImageBatch = (
  current: readonly PendingImage[],
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

export const readFileAsDataUrl = (file: File): Promise<string> =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => resolve(event.target?.result as string);
    reader.onerror = () => reject(reader.error || new Error(`读取图片“${file.name}”失败。`));
    reader.onabort = () => reject(new Error(`读取图片“${file.name}”已取消。`));
    reader.readAsDataURL(file);
  });

export const readImageBatch = async <T extends ImageFile>(
  files: readonly T[],
  concurrency: number,
  readFile: (file: T) => Promise<string>
): Promise<PendingImage[]> => {
  if (files.length === 0) return [];

  const results = new Array<PendingImage>(files.length);
  let nextIndex = 0;
  const workerCount = Math.min(positiveIntegerOr(concurrency, 1), files.length);

  const worker = async () => {
    while (nextIndex < files.length) {
      const index = nextIndex;
      nextIndex += 1;
      const file = files[index];
      const dataUrl = await readFile(file);
      results[index] = { dataUrl, name: file.name, size: file.size };
    }
  };

  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  return results;
};

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
