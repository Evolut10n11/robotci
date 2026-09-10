from robotci.platform import current_platform


def test_windows_supports_core_without_ros_runtime() -> None:
    info = current_platform("Windows")

    assert info.core_supported
    assert not info.ros_runtime_supported


def test_linux_supports_core_and_ros_runtime() -> None:
    info = current_platform("Linux")

    assert info.core_supported
    assert info.ros_runtime_supported


def test_unknown_platform_is_not_officially_supported() -> None:
    info = current_platform("Plan9")

    assert not info.core_supported
    assert not info.ros_runtime_supported
