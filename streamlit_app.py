import os
from pathlib import Path
import runpy


def _locate_ui_script() -> Path:
    script_root = Path(__file__).resolve()
    search_paths = [script_root.parent, *script_root.parents, Path.cwd()]
    tried = []
    for directory in search_paths:
        candidate = directory / "Source" / "name_matchingUI.py"
        tried.append(candidate)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Could not locate Source/name_matchingUI.py.\n"
        + "\n".join(f"  {path}" for path in tried)
    )


_ui_script = _locate_ui_script()
APP_PATH = _ui_script.as_posix() if os.name != "nt" else str(_ui_script)
runpy.run_path(APP_PATH, run_name="__main__")
