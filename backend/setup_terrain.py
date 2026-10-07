"""Download and verify the global LOLA elevation dataset (506 MiB)."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import ssl
import tempfile

import certifi
import httpx

from backend.setup_kernels import file_hash
from backend.terrain.global_dem import SOURCE, dem_path

DEM_SHA256 = "0f40bce8b42864deddb6943a38474879e691d5b20647aa5e54c2612b23106499"


@contextmanager
def download_stream():
    # NASA SVS is dual-stack; explicitly use IPv4 for networks with broken IPv6 TLS.
    context = ssl.create_default_context(cafile=certifi.where())
    transport = httpx.HTTPTransport(verify=context, local_address="0.0.0.0")
    with httpx.Client(transport=transport, timeout=httpx.Timeout(120, connect=20), follow_redirects=True) as client:
        with client.stream("GET", SOURCE, headers={"User-Agent": "CLPS-Lunar-Browser/1.0"}) as response:
            response.raise_for_status()
            yield response


def setup_terrain(path: Path, check_only: bool = False) -> None:
    path = Path(path)
    if path.is_file() and file_hash(path) == DEM_SHA256:
        print("Verified global LOLA DEM")
        return
    if check_only:
        raise ValueError("Missing or incorrect global LOLA DEM")
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as file:
                temporary = Path(file.name)
                with download_stream() as response:
                    for chunk in response.iter_bytes(1024 * 1024):
                        file.write(chunk)
            if file_hash(temporary) != DEM_SHA256:
                raise ValueError("SHA-256 mismatch for global DEM; existing file left unchanged")
            temporary.replace(path)
            print("Downloaded and verified global LOLA DEM")
            return
        except (OSError, ValueError, httpx.HTTPError):
            if attempt == 2:
                raise
            print("Retrying global DEM after an incomplete or failed download")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=dem_path())
    parser.add_argument("--check", action="store_true", help="verify without downloading")
    args = parser.parse_args()
    try:
        setup_terrain(args.path, args.check)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        parser.exit(1, f"Terrain setup failed: {exc}\n")


if __name__ == "__main__":
    main()
