# -*- coding: utf-8 -*-
"""设备契约：一把键盘设备必须提供什么、可以额外提供什么。

为什么用 ``abc.ABC`` 而不是 ``typing.Protocol``：目标机是 Python 3.8，
Protocol 只在类型检查器里生效，运行时缺项不会报错；而这里的目的是**约束实现**
（换键盘时漏实现一项就要立刻发现），所以用继承 + ``@abstractmethod``，
缺任何必需项时实例化直接 ``TypeError``。

契约分七组，顺序如下：

1. 身份 —— ``name`` / ``vid`` / ``pid``
2. 接口角色 —— ``is_keyboard_interface`` / ``is_consumer_interface`` / 端点预期
3. 键盘报告 —— 布局元数据 + ``parse_key_report`` + 读取长度
4. 消费类报告 —— Report ID / usage 布局 + 取舍规则 + 解析 + 读取长度（可选）
5. 键表与层 —— 层表、层顺序、层切换键与切层语义
6. 重复策略 —— 哪些键参与自动重复（可选）
7. 指示灯能力 —— 输出报告打包与轮询能力（可选）

只有"没有它就跑不起来"的成员是 ``@abstractmethod``；第 4、6、7 组属于可选能力，
基类给出默认实现，默认值等价于"该设备没有这项能力"。子类覆写即可声明具备该能力，
并在覆写处的 docstring 里说明本设备的实测语义。
"""

from abc import ABC, abstractmethod


class KeyboardDevice(ABC):
    """一个键盘设备的契约。

    子类代表**一把具体的键盘**，只放实测值；通用代码（keyboard.py /
    keyboard_utils.py / tools）只通过包入口导出的名字使用它，不直接引用子类。
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
    # 5. 键表与层
    # ============================================================
    @property
    @abstractmethod
    def layers(self):
        """层名 → ``{HID usage: VK}`` 的映射表，至少一层，且每层非空。"""

    @property
    def layer_order(self):
        """层的轮转顺序（可迭代的层名序列）。默认取 ``layers`` 的插入顺序。"""
        return tuple(self.layers)

    @property
    def default_layer_name(self):
        """启动时的层名。默认 ``layer_order`` 的第一个。"""
        order = tuple(self.layer_order)
        return order[0] if order else ''

    @property
    def layer_toggle_hid(self):
        """层切换键的 HID usage；``None`` 表示该设备没有层切换键（默认）。"""
        return None

    def is_layer_toggle(self, hid_code):
        """是否为层切换键。默认与 ``layer_toggle_hid`` 比较，未声明时恒 ``False``。

        层切换键的语义由通用代码保证：只在"上一份报告未按下 → 本次按下"时切换一次，
        不注入系统、不参与自动重复。
        """
        return self.layer_toggle_hid is not None and hid_code == self.layer_toggle_hid

    def next_layer_name(self, current_name):
        """按 ``layer_order`` 轮转下一层；未知层名回到默认层，只有一层时返回原名。"""
        order = tuple(self.layer_order)
        if not order:
            return self.default_layer_name
        try:
            index = order.index(current_name)
        except ValueError:
            return self.default_layer_name
        return order[(index + 1) % len(order)]

    def get_vk(self, layer_name, hid_code):
        """按层取虚拟键码，未映射返回 ``None``。默认查 ``layers``。"""
        layer = self.layers.get(layer_name)
        if layer is None:
            return None
        return layer.get(hid_code)

    @property
    def consumer_map(self):
        """消费类 usage → VK 的映射表。默认空表（没有媒体键）。"""
        return {}

    def get_consumer_vk(self, usage):
        """消费类 usage → VK，未映射返回 ``None``。默认查 ``consumer_map``。"""
        return self.consumer_map.get(usage)

    @property
    def keymap_subsets(self):
        """构成 ``layers`` 的命名子表（如 C/XL/XN），只供文档与一致性自检使用。

        默认空。若提供，自检要求每个子表至少被某一层完整包含，避免改了子表却
        忘了重新合并进层表。
        """
        return {}

    # ============================================================
    # 6. 重复策略（可选）
    # ============================================================
    @property
    def no_repeat_vks(self):
        """不参与自动重复的 VK 集合（如锁定键）。默认空集。"""
        return frozenset()

    @property
    def repeat_consumer_vks(self):
        """参与长按重复的消费类 VK。默认为空（消费类只在按下/抬起各上报一次）。"""
        return ()

    def repeats_key(self, vk):
        """普通键/修饰键是否参与自动重复。默认：非空且不在 ``no_repeat_vks``。"""
        return vk is not None and vk not in self.no_repeat_vks

    def repeats_consumer(self, vk):
        """消费类键是否参与长按重复。默认：在 ``repeat_consumer_vks`` 内。"""
        return vk in self.repeat_consumer_vks

    # ============================================================
    # 7. 指示灯能力（可选）
    # ============================================================
    @property
    def led_supported(self):
        """是否声明指示灯可控。默认 ``False``：默认关闭，只有显式 ``--led`` 才尝试。"""
        return False

    @property
    def led_report_length(self):
        """HID 输出报告字节数。默认 1。"""
        return 1

    @property
    def led_poll_interval_s(self):
        """锁定状态兜底轮询间隔（秒）。默认 0.2，避免无谓的 USB 流量。"""
        return 0.2

    @property
    def led_bits(self):
        """``(bit, vk)`` 序列，描述 LED 位序。默认空（不声明位定义）。"""
        return ()

    @property
    def led_unavailable_hint(self):
        """指示灯不可用时打印给用户的说明。默认空串。"""
        return ''

    def led_report(self, bitmap):
        """把 LED 位图打包成 HID 输出报告。默认按 ``led_report_length`` 小端截断。"""
        mask = (1 << (8 * self.led_report_length)) - 1
        return int(bitmap & mask).to_bytes(self.led_report_length, 'little')
