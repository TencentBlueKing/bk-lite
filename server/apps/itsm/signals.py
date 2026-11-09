from django.dispatch import Signal

# 载荷在 M1-12 通知里约定。当前只提供可订阅的事件名。
itsm_event = Signal()
