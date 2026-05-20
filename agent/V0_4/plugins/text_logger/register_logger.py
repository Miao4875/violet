from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_spec = spec_from_file_location("text_logger_impl", Path(__file__).with_name("plugin.py"))
_module = module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_module)
register = _module.register
