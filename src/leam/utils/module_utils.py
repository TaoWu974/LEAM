import importlib.util


def optional_module_available(module_name: str) -> bool:
    """Return whether an optional module can be imported safely."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False
