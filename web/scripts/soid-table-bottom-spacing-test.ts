import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const soidPagePath =
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/featureLibrary/soid/page.tsx';
const assetDataPagePath = 'src/app/cmdb/(pages)/assetData/page.tsx';

const soidSource = readFileSync(soidPagePath, 'utf8');
const assetDataSource = readFileSync(assetDataPagePath, 'utf8');

const readSoidOffset = (source: string) => {
  const match = source.match(/calc\(100vh - (\d+)px\)/);
  assert.ok(match, '未找到 SOID 表格高度偏移');
  return Number(match[1]);
};

const readAssetOffsetWithoutFilter = (source: string) => {
  const match = source.match(
    /storeQueryList\.length > 0[\s\S]*?\? 'calc\(100vh - \d+px\)'[\s\S]*?: 'calc\(100vh - (\d+)px\)'/
  );
  assert.ok(match, '未找到资产实例列表无筛选条件时的表格高度偏移');
  return Number(match[1]);
};

const viewportHeight = 800;
const paginationHeight = 56;
const soidLayout = {
  top: 204,
  headerHeight: 55,
  offset: readSoidOffset(soidSource),
};
const assetLayout = {
  top: 143,
  headerHeight: 47,
  offset: readAssetOffsetWithoutFilter(assetDataSource),
};

const getBottomGap = ({
  top,
  headerHeight,
  offset,
}: {
  top: number;
  headerHeight: number;
  offset: number;
}) =>
  viewportHeight -
  (top + (viewportHeight - offset) + headerHeight + paginationHeight);

const soidBottomGap = getBottomGap(soidLayout);
const assetBottomGap = getBottomGap(assetLayout);
const gapDifference = Math.abs(soidBottomGap - assetBottomGap);

assert.ok(
  gapDifference <= 2,
  `SOID 底部留白 ${soidBottomGap}px，资产实例列表 ${assetBottomGap}px，差值 ${gapDifference}px`
);

console.log(
  `SOID 底部留白 ${soidBottomGap}px，资产实例列表 ${assetBottomGap}px，差值 ${gapDifference}px`
);
