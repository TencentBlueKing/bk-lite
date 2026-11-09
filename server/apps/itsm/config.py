# 调度在对应任务落地后再写入。M1-02 只保留空表，避免 beat 指向尚未实现的任务。
CELERY_BEAT_SCHEDULE = {}
