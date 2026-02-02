# -- coding: utf-8 --
# @File: validators.py
# @Time: 2026/1/14
# @Author: windyzhao
"""
CQL参数验证器
用于验证不能参数化的CQL组成部分（标签、字段名、关系类型）
防止注入攻击
"""
import re
from typing import Any, List
from apps.core.exceptions.base_app_exception import BaseAppException


class CQLValidator:
    """CQL参数安全验证器"""
    
    # 白名单正则：标签可以包含字母、数字、下划线、中文
    LABEL_PATTERN = re.compile(r'^[\w\u4e00-\u9fa5]+$')
    
    # 白名单正则：字段名只能是字母、数字、下划线，且以字母或下划线开头
    FIELD_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    
    # 关系类型白名单（同标签规则）
    RELATION_PATTERN = re.compile(r'^[\w\u4e00-\u9fa5]+$')
    
    @staticmethod
    def validate_id(value: Any) -> int:
        """
        验证并强制转换ID为整数
        
        Args:
            value: 待验证的ID值
            
        Returns:
            int: 验证通过的整数ID
            
        Raises:
            BaseAppException: ID无效时抛出
        """
        try:
            int_value = int(value)
            if int_value < 0:
                raise ValueError("ID must be non-negative")
            return int_value
        except (ValueError, TypeError) as e:
            raise BaseAppException(f"Invalid ID value: {value}, error: {str(e)}")
    
    @staticmethod
    def validate_ids(value: Any) -> List[int]:
        """
        验证并转换ID列表
        
        Args:
            value: 待验证的ID列表
            
        Returns:
            List[int]: 验证通过的整数ID列表
        """
        if not isinstance(value, (list, tuple)):
            raise BaseAppException(f"IDs must be a list or tuple, got: {type(value)}")
        
        if not value:
            raise BaseAppException("ID list cannot be empty")
        
        return [CQLValidator.validate_id(v) for v in value]
    
    @staticmethod
    def validate_label(label: str) -> str:
        """
        验证标签名称（不能参数化，必须白名单验证）
        
        Args:
            label: 标签名称
            
        Returns:
            str: 验证通过的标签名
        """
        if not label:
            raise BaseAppException("Label cannot be empty")
        
        if not isinstance(label, str):
            raise BaseAppException(f"Label must be string, got: {type(label)}")
        
        if not CQLValidator.LABEL_PATTERN.match(label):
            raise BaseAppException(
                f"Invalid label name: '{label}'. "
                f"Label must contain only letters, numbers, underscores, or Chinese characters"
            )
        
        return label
    
    @staticmethod
    def validate_field(field: str) -> str:
        """
        验证字段名称（不能参数化，必须白名单验证）
        
        Args:
            field: 字段名称
            
        Returns:
            str: 验证通过的字段名
        """
        if not field:
            raise BaseAppException("Field name cannot be empty")
        
        if not isinstance(field, str):
            raise BaseAppException(f"Field name must be string, got: {type(field)}")
        
        if not CQLValidator.FIELD_PATTERN.match(field):
            raise BaseAppException(
                f"Invalid field name: '{field}'. "
                f"Field must start with letter/underscore and contain only alphanumeric/underscore"
            )
        
        return field
    
    @staticmethod
    def validate_relation(relation: str) -> str:
        """
        验证关系类型名称
        
        Args:
            relation: 关系类型
            
        Returns:
            str: 验证通过的关系类型
        """
        if not relation:
            raise BaseAppException("Relation type cannot be empty")
        
        if not isinstance(relation, str):
            raise BaseAppException(f"Relation must be string, got: {type(relation)}")
        
        if not CQLValidator.RELATION_PATTERN.match(relation):
            raise BaseAppException(
                f"Invalid relation name: '{relation}'. "
                f"Relation must contain only letters, numbers, underscores, or Chinese characters"
            )
        
        return relation
    
    @staticmethod
    def validate_order_type(order_type: str) -> str:
        """验证排序类型"""
        allowed = {'ASC', 'DESC'}
        order_upper = order_type.upper() if order_type else 'ASC'
        
        if order_upper not in allowed:
            raise BaseAppException(f"Order type must be ASC or DESC, got: {order_type}")
        
        return order_upper
