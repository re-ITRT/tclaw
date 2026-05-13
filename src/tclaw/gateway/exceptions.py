"""Gateway 异常定义。"""


class ComponentError(Exception):
    """组件相关异常的基类。"""


class ComponentNotSupported(ComponentError):
    """当前运行时环境不支持交互组件。"""
    def __init__(self, message: str = "interactive components not supported in this environment"):
        self.message = message
        super().__init__(message)


class ComponentTimeout(ComponentError):
    """等待组件回调超时。"""
    def __init__(self, component_id: str):
        self.component_id = component_id
        super().__init__(f"component {component_id} timed out")


class ComponentNotFound(ComponentError):
    """组件未找到。"""
    def __init__(self, component_id: str):
        self.component_id = component_id
        super().__init__(f"component not found: {component_id}")
