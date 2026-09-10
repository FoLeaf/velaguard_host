from dataclasses import dataclass, field
from typing import Any

@dataclass
class DataSourceConfig:
    """用于存储单个数据源配置信息和关联的UI卡片对象"""
    source_id: int
    name: str
    port: str
    baud_rate: int
    is_active: bool = False
    card_widget: Any = None  # 存储与此数据源关联的UI卡片对象

# 这是一个示例，展示如何使用它
if __name__ == '__main__':
    # 1. 创建一个列表来存储所有数据源配置 (相当于结构体数组)
    all_sources = []

    # 2. 创建两个数据源配置实例
    source1 = DataSourceConfig(source_id=1, name="温度传感器", port="COM1", baud_rate=9600)
    source2 = DataSourceConfig(source_id=2, name="湿度传感器", port="COM3", baud_rate=115200, is_active=True)

    # 3. 将它们添加到列表中
    all_sources.append(source1)
    all_sources.append(source2)

    # 4. 访问和操作数据
    print(f"总共有 {len(all_sources)} 个数据源。")

    # 遍历并打印每个数据源的信息
    for source in all_sources:
        print(f"  - ID: {source.source_id}, 名称: {source.name}, 端口: {source.port}, 状态: {'激活' if source.is_active else '未激活'}")

    # 修改其中一个数据源的状态
    print("\n激活第一个数据源...")

    all_sources[0].is_active = True

    print(f"ID: {all_sources[0].source_id} 的新状态: {'激活' if all_sources[0].is_active else '未激活'}")
