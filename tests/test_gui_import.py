import pytest


def test_app_importable():
    try:
        from tradebot_sci.gui import app  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("GUI module (tradebot_sci.gui) not installed")
    except ImportError as e:
        pytest.fail(f"GUI app failed to import: {e}")
