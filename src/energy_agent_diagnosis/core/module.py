"""定义单进程内可独立初始化、未来可拆分的逻辑模块。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class LogicalModule:
    """记录逻辑模块初始化状态，为后续独立服务保留生命周期边界。"""

    name: str
    initialized: bool = field(default=False, init=False)

    async def initialize(self) -> None:
        """初始化模块；阶段 1 不连接业务数据源。"""
        self.initialized = True

    async def shutdown(self) -> None:
        """按与初始化相反的顺序释放模块资源。"""
        self.initialized = False
