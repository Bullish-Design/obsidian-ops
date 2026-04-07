from obsidian_ops import __version__


def test_package_version_present() -> None:
    assert __version__ == "0.1.0"
