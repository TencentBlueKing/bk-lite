def chunks(items: list, size: int):
    """按固定大小切分，供监控映射和告警摘要分批查询。"""
    for index in range(0, len(items), size):
        yield items[index : index + size]
