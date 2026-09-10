export interface ImageRecord {
  image_name: string;
  image_url: string;
  label?: string;
  predicted_label?: string;
}

export interface AppendImageInput {
  fileName: string;
  blob: Blob;
  imageUrl: string;
}

export type AppendImageResult =
  | { accepted: true }
  | { accepted: false; reason: 'duplicate_name' };

export const hasImageNameConflict = (
  blobs: Map<string, Blob>,
  trainData: readonly Pick<ImageRecord, 'image_name'>[],
  fileName: string,
): boolean => {
  if (blobs.has(fileName)) {
    return true;
  }
  return trainData.some((item) => item.image_name === fileName);
};

export const tryAppendImage = (
  blobs: Map<string, Blob>,
  trainData: ImageRecord[],
  input: AppendImageInput,
): AppendImageResult => {
  if (hasImageNameConflict(blobs, trainData, input.fileName)) {
    return { accepted: false, reason: 'duplicate_name' };
  }
  blobs.set(input.fileName, input.blob);
  trainData.push({
    image_name: input.fileName,
    image_url: input.imageUrl,
  });
  return { accepted: true };
};
