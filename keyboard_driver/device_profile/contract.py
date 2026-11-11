# -*- coding: utf-8 -*-
"""设备契约：一把键盘设备必须提供什么、可以额外提供什么。

为什么用 ``abc.ABC`` 而不是 ``typing.Protocol``：目标机是 Python 3.8，
Protocol 只在类型检查器里生效，运行时缺项不会报错；而这里的目的是**约束实现**
（换键盘时漏实现一项就要立刻发现），所以用继承 + ``@abstractmethod``，
缺任何必需项时实例化直接 ``TypeError``。

契约只描述**报告布局类事实**（设备侧不可推导的东西），分五组：

1. 身份 —— ``name`` / ``vid`` / ``pid``
2. 接口角色 —— ``is_keyboard_interface`` / ``is_consumer_interface`` / 端点预期
3. 键盘报告 —— 布局元数据 + ``parse_key_report`` + 读取长度
4. 消费类报告 —— Report ID / usage 布局 + 取舍规则 + 解析 + 读取长度（可选）
5. 指示灯输出报告 —— Report ID / 长度 / 位定义（可选）

usage→VK 的换算、自动重复语义、锁定键处理都不属于设备事实，统一放在
``keyboard_driver/usage.py``，由主机侧按 HID Usage Tables 通用处理——与 Windows 原生
HID 键盘类的分工一致：固件自己决定上报哪些 usage，主机只做通用解释。

只有"没有它就跑不起来"的成员是 ``@abstractmethod``；第 4、5 组属于可选能力，
基类给出默认实现，默认值等价于"该设备没有这项能力"。子类覆写即可声明具备该能力，
并在覆写处的 docstring 里说明本设备的实测语义。
"""

from abc import ABC, abstractmethod


class KeyboardDevice(ABC):
    """一个键盘设备的契约。

    子类代表**一把具体的键盘**，只放实测值；通用代码（keyboard.py /
    transport.py / tools）只通过包入口导出的名字使用它，不直接引用子类。
    """

    # ============================================================
    # 1. 身份
    # ============================================================
    @property
    @abstractmethod
    def name(self):
        """人类可读的设备名（日志显示用），非空字符串。"""

    @property
    @abstractmethod
    def vid(self):
        """USB Vendor ID（0..0xFFFF），用于枚举过滤。"""

    @property
    @abstractmethod
    def pid(self):
        """USB Product ID（0..0xFFFF），用于枚举过滤。"""

    # ============================================================
    # 2. 接口角色
    # ============================================================
    # 下面是 HID 规范常量，不属于设备数据；设备描述符符合规范时子类无需覆写。
    interface_class_hid = 0x03
    keyboard_interface_subclass = 0x01
    keyboard_interface_protocol = 0x01

    @abstractmethod
    def is_keyboard_interface(self, setting):
        """判断某个接口设置是否承担键盘角色。

        必须按描述符判定（类/子类/协议），不要按接口号：复合设备由 usbccgp
        拆成多个同 VID/PID 的设备节点，枚举顺序不保证。
        """

    def is_consumer_interface(self, setting):
        """判断某个接口设置是否可能是消费类接口（媒体键）。

        默认语义：HID 类且不是键盘接口的接口视为消费类候选，具体集合还要由
        报告描述符确认（见 ``choose_consumer_report``）。设备完全没有消费类
        集合时，覆写为恒 ``False``。
        """
        if getattr(setting, 'bInterfaceClass', 0) != self.interface_class_hid:
            return False
        return not self.is_keyboard_interface(setting)

    @property
    def endpoint_direction(self):
        """数据端点方向：``'in'`` / ``'out'``。默认 ``'in'``（设备上报）。"""
        return 'in'

    @property
    def endpoint_type(self):
        """数据端点类型：``'interrupt'`` / ``'bulk'`` / ``'isochronous'``。

        默认 ``'interrupt'``（HID 输入报告的常规类型）。
        """
        return 'interrupt'

    # ============================================================
    # 3. 键盘报告布局与解析
    # ============================================================
    @property
    @abstractmethod
    def key_report_length(self):
        """键盘输入报告的总字节数，必须为正。

        必须与 ``parse_key_report`` 的判定一致：不足这个长度视为残包。
        """
        # 注意：与"设备专有"无关，这里只记录实测布局（例如 8 字节 boot 报告）。

    @property
    def modifier_byte_index(self):
        """修饰键位图在报告中的字节偏移。默认 0（boot 键盘首字节即修饰键）。"""
        return 0

    @property
    def key_slot_start(self):
        """键码槽起始偏移（左闭）。默认 2（前两字节为修饰键与保留字节）。"""
        return 2

    @property
    def key_slot_end(self):
        """键码槽结束偏移（右开）。默认等于 ``key_report_length``。"""
        return self.key_report_length

    @property
    def key_report_has_id(self):
        """报告首字节是否为 Report ID。默认 ``False``（boot 协议无 Report ID）。"""
        return False

    @abstractmethod
    def parse_key_report(self, raw):
        """解析键盘报告，返回 ``(修饰键字节, 键码列表)``。

        长度不足（含 ``None``）必须返回 ``(0, None)``；空槽（键码 0）不进入列表。
        返回值形状是通用代码唯一的取值入口，不要改成自定义对象。
        """

    @abstractmethod
    def key_report_read_size(self, max_packet_size):
        """单次读取长度：至少覆盖完整报告，且不小于端点最大包长。"""

    # ============================================================
    # 4. 消费类报告（媒体键，可选）
    # ============================================================
    @property
    def consumer_usage_page(self):
        """消费类集合的 Usage Page。HID 规范值 0x0C，子类一般无需覆写。"""
        return 0x0C

    @property
    def consumer_report_id(self):
        """消费类输入报告的 Report ID。默认 1。"""
        return 1

    @property
    def consumer_report_id_size(self):
        """Report ID 占用的字节数。默认 1。"""
        return 1

    @property
    def consumer_usage_size(self):
        """usage 占用的字节数。默认 2。"""
        return 2

    @property
    def consumer_usage_bits(self):
        """usage 的位宽（用于从描述符 Input 项里挑选）。默认 16。"""
        return 16

    @property
    def consumer_usage_byte_order(self):
        """usage 的字节序：``'little'`` / ``'big'``。默认 ``'little'``。"""
        return 'little'

    def choose_consumer_report(self, items):
        """从报告描述符的 Input 项里选出消费类输入报告。

        ``items`` 为 ``[(usage_page, report_id, report_size_bits), ...]``。
        返回 ``(report_id, usage_bytes)``；返回 ``None`` 表示该设备没有消费类集合
        （默认实现即恒 ``None``）。同一描述符里若混有别的 0x0C 输入项（例如鼠标的
        8 位 AC Pan），取舍规则写在这里。
        """
        return None

    def consumer_report_read_size(self, max_packet_size):
        """消费类单次读取长度：至少覆盖 Report ID + usage，且不小于端点包长。"""
        return max(self.consumer_report_id_size + self.consumer_usage_size,
                   max_packet_size)

    def parse_consumer_report(self, raw):
        """解析消费类报告，返回 usage；不是消费类报告（Report ID 不符/长度不足）返回 ``None``。

        默认实现恒 ``None``（等价于不支持消费类）。端点混流时必须按 Report ID 过滤。
        """
        return None

    # ============================================================
    # 5. 指示灯输出报告（可选）
    # ============================================================
    @property
    def led_supported(self):
        """是否声明指示灯输出报告可写。

        默认 ``False``。声明为 ``True`` 表示主机应当把系统锁定状态
        （Num/Caps/Scroll）写回设备——这是原生 HID 键盘类驱动的标准行为，
        有些固件还会据此切换上报的键值（例如 Num Lock 时把字母区改报小键盘）。
        """
        return False

    @property
    def led_report_id(self):
        """LED 输出报告的 Report ID。默认 0（描述符未给 LED 段分配 Report ID）。"""
        return 0

    @property
    def led_report_length(self):
        """HID 输出报告字节数。默认 1。"""
        return 1

    @property
    def led_poll_interval_s(self):
        """锁定状态兜底轮询间隔（秒）。默认 0.2；轮询只读系统状态，不变就不写 USB。"""
        return 0.2

    @property
    def led_bits(self):
        """``(bit, vk)`` 序列，描述 LED 位序。默认空（不声明位定义）。"""
        return ()

    def led_report(self, bitmap):
        """把 LED 位图打包成 HID 输出报告。

        默认按 ``led_report_length`` 小端截断；``led_report_id`` 非 0 时把 Report ID
        作为首字节前置（HID Set_Report 的两种惯例之一，视设备描述符而定）。
        """
        mask = (1 << (8 * self.led_report_length)) - 1
        payload = int(bitmap & mask).to_bytes(self.led_report_length, 'little')
        if self.led_report_id:
            return bytes([self.led_report_id]) + payload
        return payload
