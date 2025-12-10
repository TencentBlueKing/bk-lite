# -*- coding: utf-8 -*-
"""
Webhook 客户端工具类
统一管理 Lab 环境的 webhook 请求
"""

import os
from apps.core.logger import opspilot_logger as logger


class WebhookClient:
    """Webhook 客户端,用于构建和管理 webhook URL"""
    
    @staticmethod
    def get_base_url():
        """
        获取 webhook 基础 URL
        
        Returns:
            str: webhook 基础 URL,如果未配置则返回 None
        """
        webhook_base_url = os.getenv('WEBHOOK', None)
        
        if not webhook_base_url:
            logger.warning("环境变量 WEBHOOK 未配置")
            return None
        
        # 确保 URL 以 / 结尾
        if not webhook_base_url.endswith('/'):
            webhook_base_url += '/'
        
        return webhook_base_url
    
    @staticmethod
    def get_runtime():
        """
        获取 Lab 运行时类型
        
        Returns:
            str: 'docker' 或 'kubernetes',默认为 'kubernetes'
        """
        return os.getenv("LAB_RUNTIME", "kubernetes")
    
    @staticmethod
    def build_url(endpoint_name):
        """
        构建完整的 webhook URL
        
        Args:
            endpoint_name: 端点名称,如 'setup', 'start', 'stop', 'status'
            
        Returns:
            str: 完整的 webhook URL,如果配置缺失则返回 None
            
        Examples:
            >>> WebhookClient.build_url('setup')
            'http://webhook-server:8080/compose/setup'
        """
        base_url = WebhookClient.get_base_url()
        
        if not base_url:
            return None
        
        runtime = WebhookClient.get_runtime()
        
        # 根据运行时类型添加路径前缀
        if runtime == "docker":
            full_url = f"{base_url}compose/{endpoint_name}"
        elif runtime == "kubernetes":
            full_url = f"{base_url}kubernetes/{endpoint_name}"
        else:
            logger.warning(f"未知的运行时类型: {runtime}, 使用默认路径")
            full_url = f"{base_url}{endpoint_name}"
        
        logger.debug(f"构建 webhook URL: {full_url}")
        return full_url
    
    @staticmethod
    def validate_config():
        """
        验证 webhook 配置是否完整
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not os.getenv('WEBHOOK'):
            return False, "环境变量 WEBHOOK 未配置"
        
        runtime = WebhookClient.get_runtime()
        if runtime not in ['docker', 'kubernetes']:
            return False, f"环境变量 LAB_RUNTIME 值无效: {runtime}, 应为 'docker' 或 'kubernetes'"
        
        return True, ""
    
    @staticmethod
    def get_all_endpoints():
        """
        获取所有可用的 webhook 端点
        
        Returns:
            dict: 端点名称到完整 URL 的映射
        """
        endpoints = ['setup', 'start', 'stop', 'status']
        return {name: WebhookClient.build_url(name) for name in endpoints}
