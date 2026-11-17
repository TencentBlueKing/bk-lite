interface ListPage {
  items: unknown[];
  count?: number;
  [key: string]: unknown;
}

/** 管理列表和选择器完整读取分页接口，并保留首响应的权限信息。 */
export async function readListPages(read: (page: number) => Promise<unknown>): Promise<ListPage> {
  const first = await read(1) as ListPage;
  const items = [...first.items];
  let page = 1;
  while (items.length < (first.count ?? items.length)) {
    const next = await read(++page) as ListPage;
    if (!next.items.length) break;
    items.push(...next.items);
  }
  return { ...first, items };
}
