import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { tryAppendImage } from '../src/app/mlops/components/annotation/imageNameConflict';

interface ImageRecord {
  image_name: string;
  image_url: string;
  label?: string;
}

const packZipLike = (trainData: ImageRecord[], blobs: Map<string, Blob>) => {
  const zip = new Map<string, Blob>();
  trainData.forEach((item) => {
    const blob = blobs.get(item.image_name);
    if (blob) {
      zip.set(item.image_name, blob);
    }
  });
  return zip;
};

const oldBlob = new Blob(['old-pixels'], { type: 'image/jpeg' });
const newBlob = new Blob(['new-pixels'], { type: 'image/jpeg' });
const blobs = new Map<string, Blob>([['a.jpg', oldBlob]]);
const trainData: ImageRecord[] = [
  { image_name: 'a.jpg', image_url: 'blob:old', label: 'cat' },
];

const conflictResult = tryAppendImage(blobs, trainData, {
  fileName: 'a.jpg',
  blob: newBlob,
  imageUrl: 'blob:new',
});

assert.equal(
  blobs.get('a.jpg'),
  oldBlob,
  'same-name append must keep the original Blob; overwriting would make save pack the new content',
);
assert.equal(conflictResult.accepted, false, 'same-name append must be rejected');
assert.equal(trainData.length, 1, 'must not append a second record for the same image_name');
assert.equal(trainData[0].label, 'cat', 'original label must stay on the original image');
assert.notEqual(blobs.get('a.jpg'), newBlob, 'two records must not share the new Blob');

const packedAfterConflict = packZipLike(trainData, blobs);
assert.equal(packedAfterConflict.size, 1);
assert.equal(
  packedAfterConflict.get('a.jpg'),
  oldBlob,
  'handleSave-style ZIP packing must still emit the original a.jpg bytes',
);

const uniqueBlob = new Blob(['unique-pixels'], { type: 'image/jpeg' });
const uniqueResult = tryAppendImage(blobs, trainData, {
  fileName: 'b.jpg',
  blob: uniqueBlob,
  imageUrl: 'blob:unique',
});

assert.equal(uniqueResult.accepted, true, 'a unique filename must still be appended');
assert.equal(blobs.get('a.jpg'), oldBlob, 'adding a unique name must not touch the original Blob');
assert.equal(blobs.get('b.jpg'), uniqueBlob);
assert.equal(trainData.length, 2);
assert.equal(trainData[1].image_name, 'b.jpg');

const packedAfterUnique = packZipLike(trainData, blobs);
assert.equal(packedAfterUnique.get('a.jpg'), oldBlob);
assert.equal(packedAfterUnique.get('b.jpg'), uniqueBlob);

const root = process.cwd();
const imageContent = fs.readFileSync(
  path.join(root, 'src/app/mlops/components/annotation/imageContent.tsx'),
  'utf8',
);
const addNewImageStart = imageContent.indexOf('const addNewImage');
assert.ok(addNewImageStart >= 0, 'imageContent.tsx must define addNewImage');
const addNewImage = imageContent.slice(addNewImageStart);
const conflictIdx = addNewImage.indexOf('hasImageNameConflict');
const setIdx = addNewImage.indexOf('imageBlobsRef.current.set(fileName, blob)');
assert.ok(conflictIdx >= 0, 'addNewImage must consult hasImageNameConflict');
assert.ok(
  setIdx > conflictIdx,
  'Blob Map write must happen after the name-conflict check',
);
assert.match(addNewImage, /datasets\.imageNameConflict/);

const zh = JSON.parse(fs.readFileSync(path.join(root, 'src/app/mlops/locales/zh.json'), 'utf8'));
const en = JSON.parse(fs.readFileSync(path.join(root, 'src/app/mlops/locales/en.json'), 'utf8'));
assert.ok(zh.datasets.imageNameConflict, 'missing zh datasets.imageNameConflict');
assert.ok(en.datasets.imageNameConflict, 'missing en datasets.imageNameConflict');

console.log('mlops image name conflict test passed');
