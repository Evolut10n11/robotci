import subprocess
import sys


def test_cli_import_does_not_load_ros_modules() -> None:
    code = (
        "import sys; "
        "import robotci.cli; "
        "assert 'rclpy' not in sys.modules; "
        "assert 'nav2_simple_commander' not in sys.modules"
    )

    subprocess.run([sys.executable, "-c", code], check=True)
