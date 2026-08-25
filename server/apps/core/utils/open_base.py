from functools import wraps
from typing import Any, Callable, Optional

from apps.core.logger import logger
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ViewSet

LOGIN_EXEMPT_ATTR = 'login_exempt'


def login_exempt(view_func: Callable) -> Callable:
    """
    标记视图函数免于登录保护的装饰器
    
    Args:
        view_func: 需要豁免登录的视图函数
        
    Returns:
        装饰后的视图函数
        
    Raises:
        TypeError: 当传入的不是可调用对象时
    """
    if not callable(view_func):
        raise TypeError("login_exempt装饰器只能应用于可调用对象")
    
    @wraps(view_func)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        """包装后的视图函数"""
        return view_func(*args, **kwargs)
    
    setattr(wrapped_view, LOGIN_EXEMPT_ATTR, True)
    return wrapped_view


class OpenAPIViewSet(ViewSet):
    """
    开放API视图集基类
    
    提供无需身份验证的API接口基础功能，自动豁免CSRF和登录验证
    """
    permission_classes = [AllowAny]

    @classmethod
    def as_view(cls, actions: Optional[dict] = None, **kwargs: Any) -> Callable:
        """
        创建视图实例，自动应用登录豁免和CSRF豁免
        
        Args:
            actions: 视图集的动作映射字典
            **kwargs: 其他关键字参数
            
        Returns:
            配置了豁免策略的视图函数
        """
        try:
            view = super(ViewSet, cls).as_view(actions=actions, **kwargs)
            return csrf_exempt(login_exempt(view))
        except Exception as e:
            logger.error(f"创建OpenAPIViewSet {cls.__name__} 失败: {e}")
            raise
