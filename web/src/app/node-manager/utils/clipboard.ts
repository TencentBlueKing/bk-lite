export type ClipboardCopyFailureReason =
  | 'empty'
  | 'unavailable'
  | 'failed';

export class ClipboardCopyError extends Error {
  constructor(
    public readonly reason: ClipboardCopyFailureReason,
    cause?: unknown
  ) {
    super(reason);
    this.name = 'ClipboardCopyError';
    if (cause !== undefined) {
      this.cause = cause;
    }
  }
}

export interface ClipboardEnvironment {
  writeText?: (value: string) => Promise<void>;
  fallbackCopy?: (value: string) => boolean;
}

interface ClipboardTextArea {
  value: string;
  style: Record<string, string>;
  setAttribute: (name: string, value: string) => void;
  select: () => void;
}

interface ClipboardDocument {
  createElement: (tagName: string) => ClipboardTextArea;
  body: {
    appendChild: (element: ClipboardTextArea) => unknown;
    removeChild: (element: ClipboardTextArea) => unknown;
  };
  execCommand: (command: string) => boolean;
}

export const fallbackCopyText = (
  value: string,
  documentRef: ClipboardDocument
): boolean => {
  const textArea = documentRef.createElement('textarea');
  textArea.value = value;
  textArea.setAttribute('readonly', '');
  textArea.style.position = 'fixed';
  textArea.style.opacity = '0';
  documentRef.body.appendChild(textArea);
  try {
    textArea.select();
    return documentRef.execCommand('copy');
  } finally {
    documentRef.body.removeChild(textArea);
  }
};

const browserEnvironment = (): ClipboardEnvironment => ({
  writeText:
    typeof navigator !== 'undefined' && navigator.clipboard?.writeText
      ? (value) => navigator.clipboard.writeText(value)
      : undefined,
  fallbackCopy:
    typeof document !== 'undefined'
      ? (value) =>
        fallbackCopyText(
          value,
          document as unknown as ClipboardDocument
        )
      : undefined,
});

export const copyText = async (
  value: string,
  environment: ClipboardEnvironment = browserEnvironment()
): Promise<void> => {
  if (!value.trim()) {
    throw new ClipboardCopyError('empty');
  }

  try {
    if (environment.writeText) {
      await environment.writeText(value);
      return;
    }
    if (!environment.fallbackCopy) {
      throw new ClipboardCopyError('unavailable');
    }
    if (!environment.fallbackCopy(value)) {
      throw new ClipboardCopyError('failed');
    }
  } catch (error) {
    if (error instanceof ClipboardCopyError) {
      throw error;
    }
    throw new ClipboardCopyError('failed', error);
  }
};
