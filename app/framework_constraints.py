"""预置框架/库的 API 约束，供代码生成阶段注入到 prompt，避免生成不兼容代码。"""

# 框架标识 -> 约束条目列表（生成时按顺序拼成一段说明）
FRAMEWORK_CONSTRAINTS: dict[str, list[str]] = {
    "PyQt5": [
        "pyqtSignal() 仅接受 Qt 元对象系统支持的类型：int、str、float、bool、object，或逗号分隔的多个此类类型（如 pyqtSignal(str, int)）。",
        "不可使用 typing 泛型作为信号参数，如 tuple[str, str]、list[float]、list[float], str 等会报错；复合类型请用 object，发射时再传具体值（如 emit((a, b))）。",
        "GUI 更新必须在主线程；若在子线程中需更新 UI，使用 QMetaObject.invokeMethod 或 signals/slots 将操作转到主线程。",
    ],
    "PyQt6": [
        "pyqtSignal() 仅接受 Qt 元对象系统支持的类型：int、str、float、bool、object，或逗号分隔的多个此类类型。",
        "不可使用 typing 泛型作为信号参数（如 tuple[str, str]、list[float]）；复合类型用 object，发射时传具体值。",
        "GUI 更新必须在主线程；跨线程更新 UI 需通过 signals/slots 或 QMetaObject.invokeMethod。",
    ],
    "tkinter": [
        "主线程运行 mainloop，长时间操作会阻塞 UI；耗时任务应放在线程或使用 after() 分步执行。",
        "跨线程更新 GUI 需通过 queue 或 after() 在主线程中执行，不可在非主线程直接操作 widget。",
    ],
}


def get_constraints_for_frameworks(frameworks: list[str]) -> str:
    """
    根据框架标识列表返回合并后的约束说明文本。
    frameworks 中的字符串会做大小写不敏感匹配（如 PyQt5、pyqt5 均匹配 PyQt5）。
    """
    if not frameworks:
        return "（无）"
    seen: set[str] = set()
    lines: list[str] = []
    key_lower = {k.lower(): k for k in FRAMEWORK_CONSTRAINTS}
    for f in frameworks:
        if not f or not isinstance(f, str):
            continue
        key = key_lower.get(f.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        constraints = FRAMEWORK_CONSTRAINTS[key]
        lines.append(f"【{key}】")
        for c in constraints:
            lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines).strip() if lines else "（无）"
