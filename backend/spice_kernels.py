import os
from pathlib import Path
from threading import RLock

import spiceypy
from spiceypy.utils.exceptions import SpiceyError


SPICE_LOCK = RLock()
KERNEL_FILES = (
    "naif0012.tls",
    "de440s.bsp",
    "pck00011.tpc",
    "moon_pa_de440_200625.bpc",
    "moon_de440_220930.tf",
)
_loaded_paths: set[Path] = set()


class KernelError(RuntimeError):
    pass


def kernel_directory() -> Path:
    configured = os.environ.get("SPICE_KERNELS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent / "kernels"


def load_spice_kernels() -> None:
    directory = kernel_directory()
    paths = [directory / filename for filename in KERNEL_FILES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        names = ", ".join(missing)
        raise KernelError(
            f"Missing SPICE kernels in {directory}: {names}. See backend/kernels/README.md."
        )

    with SPICE_LOCK:
        for path in paths:
            resolved_path = path.resolve()
            if resolved_path in _loaded_paths:
                continue
            try:
                spiceypy.furnsh(str(resolved_path))
            except SpiceyError as exc:
                raise KernelError(f"Could not load SPICE kernel {path.name}: {exc}") from exc
            _loaded_paths.add(resolved_path)
