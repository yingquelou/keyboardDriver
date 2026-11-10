# device_profile —— 设备描述包

本包是项目里**唯一**允许出现「当前键盘（1EA7:0066）专有常量与分支」的地方。
通用代码（`src\keyboard.py`、`src\keyboard_utils.py`、`tools\*`）只通过
`device_profile.X` 或 `from device_profile import X` 取值。

换另一把键盘时**只改这个包**：保持包名与导出名不变，其余代码不需要改。
导出名清单、可选能力与最小骨架见仓库根 `README.md` 的「接入另一把键盘」一节，
这里只说明“改哪个文件”。

## 文件划分

| 文件 | 内容 | 什么时候改 |
|---|---|---|
| `identity.py` | `NAME` / `VID` / `PID`、`is_keyboard_interface`、`is_consumer_interface`、`ENDPOINT_DIRECTION` / `ENDPOINT_TYPE` | 换设备身份、接口类/子类/协议不同、端点不是中断 IN |
| `reports.py` | 键盘报告布局与 `parse_key_report` / `key_report_read_size`；消费类 `CONSUMER_*`、`choose_consumer_report`、`consumer_report_read_size`、`parse_consumer_report` | 报告长度/修饰键位置/键槽区间不同；消费类 Report ID、usage 位宽与字节序不同；描述符里有多个 0x0C 输入项需要取舍 |
| `keys.py` | `C` / `XL` / `XN` / `CONSUMER` 四张映射表、`LAYERS`、`LAYER_ORDER`、`DEFAULT_LAYER_NAME`、`LAYER_TOGGLE_HID`、`is_layer_toggle`、`next_layer_name`、`get_vk` / `get_consumer_vk` | **最常见的改动**：键位映射、层名与顺序、层切换键的 HID 码 |
| `policy.py` | `NO_REPEAT_VKS` / `CONSUMER_REPEAT_VKS` 与 `repeats_key` / `repeats_consumer`；`LED_*` 与 `led_report` | 重复规则不同；指示灯可用性或位序不同 |
| `_win32.py` | 私有：`win32con` 获取（pywin32 / ctypes 兼容层）与 VK 补全 | 一般不动 |
| `__init__.py` | 只做导入与 `__all__` 导出，不含实现 | 新增导出名时同步更新 |

## 约束

- 包内依赖方向是单向的：`keys.py` / `policy.py` → `_win32.py`；`identity.py`、
  `reports.py` 不依赖其它模块；`__init__.py` 只向下汇总。**不要**让子模块互相导入。
- 映射表体量大且频繁变动，必须留在 `keys.py`，不要塞回 `__init__.py`。
- `_` 开头的是私有名；通用代码只使用 `__init__.py` 导出清单里的名字。
- 改完用 `tools\calibrate.py` 逐个键核对 HID 码 → VK，用 `tools\probe_keyboard.py`
  核对接口角色与 Report ID。
