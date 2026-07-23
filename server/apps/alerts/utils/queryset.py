def iter_queryset_in_pk_batches(queryset, batch_size=200):
    """用主键游标分批物化 QuerySet，避免 ``len(queryset)`` 全量加载。"""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    last_pk = None
    while True:
        page = queryset
        if last_pk is not None:
            page = page.filter(pk__gt=last_pk)
        batch = list(page.order_by("pk")[:batch_size])
        if not batch:
            return
        yield batch
        last_pk = batch[-1].pk
