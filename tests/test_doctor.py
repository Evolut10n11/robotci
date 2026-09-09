from robotci.doctor import command_exists


def test_python_command_exists() -> None:
    assert command_exists("python3")