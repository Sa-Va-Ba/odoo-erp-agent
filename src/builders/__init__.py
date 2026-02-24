"""
Odoo Builder Agents

Two deployment options:
- OdooBuilder: Local Docker deployment
- CloudOdooBuilder: Cloud provider deployment (free tier)
"""

from .odoo_builder import OdooBuilder, BuildState, BuildTask, TaskStatus, TaskType
from .cloud_builder import CloudOdooBuilder, CloudBuildState, CloudProvider, get_available_providers

__all__ = [
    'OdooBuilder',
    'BuildState',
    'BuildTask',
    'TaskStatus',
    'TaskType',
    'CloudOdooBuilder',
    'CloudBuildState',
    'CloudProvider',
    'get_available_providers',
]
