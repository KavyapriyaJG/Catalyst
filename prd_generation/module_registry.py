import os
from typing import Dict

from langchain.tools import tool

from config import get_settings


class ModuleRegistry:
    """Per-run registry of pre-read source files grouped by module directory.

    Each pipeline run creates its own instance, so concurrent runs cannot
    corrupt each other's state.
    """

    def __init__(self):
        self._registry: Dict[str, str] = {}
        self._summary: Dict[str, Dict] = {}

    def build(self, input_path: str) -> None:
        """Walk input_path and pre-read all COBOL/config/markdown files."""
        s = get_settings()
        cobol_extensions = s.COBOL_EXTENSIONS
        other_names = s.SCAN_OTHER_NAMES
        excluded_dirs = s.SCAN_EXCLUDED_DIRS
        module_files: Dict[str, list] = {}

        for root, dirs, files in os.walk(input_path):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            for f in sorted(files):
                full = os.path.join(root, f)
                is_cobol = any(f.endswith(ext) for ext in cobol_extensions)
                is_other = f in other_names or f.lower().endswith(".md")
                if not (is_cobol or is_other):
                    continue

                rel = os.path.relpath(full, input_path)
                parts = rel.split(os.sep)
                if len(parts) >= 3:
                    module = f"{parts[0]}/{parts[1]}"
                elif len(parts) == 2:
                    module = parts[0]
                else:
                    module = "root"
                module_files.setdefault(module, []).append(full)

        total_files = 0
        total_chars = 0
        errors = []
        for module, fpaths in module_files.items():
            bundle = []
            for fpath in fpaths:
                try:
                    with open(fpath, "r", errors="replace") as fh:
                        content = fh.read()
                    rel = os.path.relpath(fpath, input_path)
                    bundle.append(f"=== FILE: {rel} ===\n{content}")
                    total_files += 1
                    total_chars += len(content)
                except Exception as e:
                    errors.append(f"{fpath}: {e}")
            self._registry[module] = "\n\n".join(bundle)
            self._summary[module] = {
                "files": len(fpaths),
                "chars": len(self._registry[module]),
            }

        print(
            f"   Found {total_files} files in {len(self._registry)} modules "
            f"({total_chars} chars total)"
        )
        if errors:
            print(f"   {len(errors)} files failed to read")
        for mod, info in sorted(self._summary.items()):
            print(f"     {mod}: {info['files']} files, {info['chars']} chars")

    def make_tools(self):
        """Return (list_modules, get_module_source) tools bound to this registry."""
        registry = self

        @tool
        def list_modules() -> dict:
            """List all available source code modules and their file counts.
            Returns a dict of module_name -> {files: N, chars: N}.
            Call this FIRST to see what modules are available for analysis."""
            print(f"   [TOOL] list_modules() called — {len(registry._summary)} modules available")
            return registry._summary

        @tool
        def get_module_source(module_name: str) -> str:
            """Get the full source code for a specific module.
            The module_name must match one returned by list_modules().
            Returns all COBOL/copybook file contents concatenated with file path headers."""
            if module_name not in registry._registry:
                print(f"   [TOOL] get_module_source('{module_name}') — NOT FOUND")
                return (
                    f"ERROR: Module '{module_name}' not found. "
                    f"Available: {list(registry._registry.keys())}"
                )
            chars = len(registry._registry[module_name])
            print(f"   [TOOL] get_module_source('{module_name}') — returning {chars} chars")
            return registry._registry[module_name]

        return list_modules, get_module_source
