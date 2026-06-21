import queris


def test_package_exposes_version() -> None:
    assert queris.__version__ == "0.1.0"
