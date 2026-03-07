import runpy
import sys
from pathlib import Path


SOURCE_REL = Path("Source") / "name_matchingUI.py"


def _find_repo_root() -> Path:
    search_dirs = [
        Path.cwd(),
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ]
    tried = []
    for directory in search_dirs:
        candidate = directory / SOURCE_REL
        tried.append(candidate)
        if candidate.is_file():
            return directory
    raise FileNotFoundError(
        "Could not locate Source/name_matchingUI.py.\n"
        + "\n".join(f"  {path}" for path in tried)
    )


repo_root = _find_repo_root()
sys.path.insert(0, str(repo_root))
runpy.run_module("Source.name_matchingUI", run_name="__main__")
