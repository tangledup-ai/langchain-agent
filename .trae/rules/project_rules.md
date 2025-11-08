# LangChain Agent 项目编写规则

## 1. 项目概述

本项目是一个基于LangChain的AI助手系统，专注于茶饮场景的智能对话和工具调用。项目采用模块化设计，支持多种LLM后端和MCP工具集成。

## 2. 编码风格规范

### 2.1 基本原则
- 代码简洁明了，避免过度设计
- 保持一致的命名约定和代码结构
- 注重可维护性和可扩展性
- 遵循Python PEP 8编码规范

### 2.2 命名约定
- 类名：PascalCase (例：`ToolManager`, `PipelineConfig`)
- 函数/变量名：snake_case (例：`get_tools`, `tool_manager`)
- 常量：UPPER_SNAKE_CASE (例：`DEFAULT_HOST`, `MAX_RETRIES`)
- 私有成员：单下划线前缀 (例：`_internal_method`)
- 特殊方法：双下划线 (例：`__init__`, `__post_init__`)

### 2.3 注释规范
- 类和公共方法必须有文档字符串
- 注释采用中英文混合，核心概念使用中文解释
- 复杂逻辑必须添加行内注释
- 文档字符串格式：
```python
def method_name(param1: str, param2: int) -> bool:
    """
    方法功能简述
    
    Args:
        param1: 参数1说明
        param2: 参数2说明
        
    Returns:
        返回值说明
    """
```

## 3. 配置管理规范

### 3.1 配置类设计
- 使用dataclass或pydantic模型定义配置类
- 所有配置类必须继承自`InstantiateConfig`或`PydanticBaseModel`
- 配置类必须包含`_target`字段，指向对应的实现类
- 配置类必须实现`setup()`方法，用于实例化目标对象

### 3.2 配置类示例
```python
@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ExampleConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ExampleClass)
    
    param1: str = "default_value"
    """参数1说明"""
    
    param2: int = 10
    """参数2说明"""
    
    def setup(self) -> ExampleClass:
        return self._target(self)
```

### 3.3 配置文件管理
- 使用YAML格式存储配置文件
- 配置文件放在`configs/`目录下
- 敏感信息(如API密钥)通过环境变量获取
- 支持配置文件覆盖和合并

## 4. Pydantic集成规范

### 4.1 使用场景
- API请求/响应模型定义
- 数据验证和序列化
- 配置管理(与dataclass并存)
- 复杂数据结构定义

### 4.2 Pydantic模型设计
- 继承自`PydanticBaseModel`基类
- 使用类型注解明确字段类型
- 提供默认值和验证规则
- 使用Field类添加元数据

### 4.3 Pydantic模型示例
```python
class ExampleModel(PydanticBaseModel):
    name: str = Field(..., description="名称")
    count: int = Field(default=0, ge=0, description="计数")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    
    class Config:
        extra = "forbid"  # 禁止额外字段
```

## 5. 工具开发规范

### 5.1 工具基类
- 所有工具必须继承自`LangToolBase`
- 实现`get_tool_fnc()`方法，返回工具函数列表
- 工具函数必须包含类型注解和文档字符串

### 5.2 工具函数规范
- 函数签名必须包含类型注解
- 参数必须有默认值和说明
- 返回值必须明确类型
- 异步函数必须标记为async

### 5.3 工具注册
- 工具通过配置类注册到`ToolManager`
- 配置类名称必须以`Config`结尾
- 工具配置必须包含`use_tool`布尔标志

## 6. 日志和错误处理

### 6.1 日志规范
- 使用loguru库进行日志记录
- 日志级别：DEBUG, INFO, WARNING, ERROR
- 关键操作必须记录INFO级别日志
- 异常必须记录ERROR级别日志

### 6.2 错误处理
- 使用try-except捕获异常
- 异常信息必须包含上下文
- 关键路径必须有异常处理
- 避免捕获过于宽泛的异常

## 7. 测试规范

### 7.1 测试结构
- 单元测试放在对应模块的`tests/`目录
- 集成测试放在项目根目录的`tests/`目录
- 测试文件名以`test_`开头

### 7.2 测试要求
- 所有公共方法必须有单元测试
- 关键业务逻辑必须有集成测试
- 测试覆盖率不低于80%
- 使用pytest框架进行测试

## 8. 文档规范

### 8.1 代码文档
- 所有模块必须有模块级文档字符串
- 公共类和方法必须有文档字符串
- 复杂算法必须有详细注释

### 8.2 项目文档
- README.md包含项目介绍和快速开始指南
- API文档放在`docs/api/`目录
- 架构文档放在`docs/architecture/`目录

## 9. 版本控制规范

### 9.1 Git提交
- 使用Conventional Commits规范
- 提交格式：`type(scope): description`
- 类型：feat, fix, docs, style, refactor, test, chore

### 9.2 分支管理
- 主分支：main
- 开发分支：develop
- 功能分支：feature/功能名
- 修复分支：fix/问题描述

## 10. 依赖管理

### 10.1 依赖规范
- 使用pyproject.toml管理项目依赖
- 生产依赖放在dependencies列表
- 开发依赖放在dev-dependencies列表
- 定期更新依赖版本

### 10.2 环境管理
- 使用虚拟环境隔离依赖
- 敏感配置通过环境变量管理
- 使用.env文件存储本地配置

## 11. 性能和安全

### 11.1 性能考虑
- 避免不必要的计算和IO操作
- 使用缓存减少重复计算
- 异步处理耗时操作
- 监控关键性能指标

### 11.2 安全规范
- 敏感信息不得硬编码
- API密钥通过环境变量获取
- 输入数据必须验证
- 遵循最小权限原则

## 12. 云端MCP集成

### 12.1 MCP配置
- 默认使用云端MCP服务：`https://xiaoliang.quant-speed.com/api/mcp/`
- 支持本地MCP服务配置覆盖
- 使用streamable-http传输协议

### 12.2 工具调用
- 通过ClientToolManager管理MCP工具
- 支持工具动态加载和调用
- 异常处理和重试机制

## 13. 代码审查

### 13.1 审查要点
- 代码风格一致性
- 功能实现正确性
- 性能和安全考虑
- 测试覆盖率

### 13.2 审查流程
- 所有代码必须经过审查
- 使用Pull Request进行审查
- 至少一人审查通过才能合并
- 自动化检查必须通过