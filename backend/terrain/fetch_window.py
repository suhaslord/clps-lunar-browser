"""Fetch verified native COG tiles for a lunar preprocessing window.

The output is a sparse source TIFF containing only the requested region. It is
not a complete source dataset and must not be used for other positions.
"""
import hashlib
import io
import json
import math
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import rasterio
import tifffile
from pyproj import CRS, Transformer
from rasterio.windows import from_bounds

from backend.calculations.sun_earth import validate_coordinates


def subset_digest(provenance):
    pinned={key:provenance[key] for key in
            ('source','source_etag','original_file_bytes','retrieved_header_sha256','tile_hashes')}
    return hashlib.sha256(json.dumps(pinned,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _range(client, url, first, last, total=None, etag=None):
    if not 0 <= first <= last or last-first+1 > 8*1024*1024:
        raise ValueError('invalid or oversized terrain byte range')
    for attempt in range(3):
        try:
            with client.stream('GET',url,headers={'Range':f'bytes={first}-{last}',
                                                'Accept-Encoding':'identity'}) as response:
                response.raise_for_status()
                parsed=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('content-range',''))
                if response.status_code!=206 or parsed is None or response.url.scheme!='https':
                    raise ValueError('source must honor HTTPS byte-range requests')
                start,end,size=map(int,parsed.groups())
                expected_last=min(last,(total if total is not None else size)-1)
                if start!=first or end!=expected_last or (total is not None and size!=total):
                    raise ValueError('source returned an incorrect byte range or changed size')
                if etag is not None and response.headers.get('etag')!=etag:
                    raise ValueError('source changed while fetching terrain tiles')
                expected=end-start+1
                payload=bytearray()
                for chunk in response.iter_bytes():
                    if len(payload)+len(chunk)>expected:
                        raise ValueError('source exceeded the requested terrain byte range')
                    payload.extend(chunk)
                if len(payload)!=expected:
                    raise ValueError('source returned an incomplete terrain tile')
                return bytes(payload),size,response.headers.get('etag')
        except (httpx.HTTPError,ValueError):
            if attempt==2:
                raise
    raise RuntimeError('unreachable byte-range retry')


def fetch_window(source_url, latitude, longitude, radius_m, output: Path):
    validate_coordinates(latitude,longitude)
    if not isinstance(source_url,str) or not source_url.startswith('https://'):
        raise ValueError('terrain source must use HTTPS')
    if not math.isfinite(radius_m) or not 0 < radius_m <= 100000:
        raise ValueError('subset radius must be positive and at most 100 km')
    # Keep the native 10%-margin selection local to the poles. Preprocessing
    # separately validates projection scale and exact coverage of its window.
    if abs(latitude) < 75:
        raise ValueError('COG subset fetching supports locations poleward of 75 degrees')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent,prefix=output.name+'.',suffix='.partial.tif',delete=False) as file:
        partial=Path(file.name)
    try:
        with httpx.Client(timeout=30,follow_redirects=True,limits=httpx.Limits(max_connections=8)) as client:
            header,total,etag = _range(client,source_url,0,1048575)
            if not etag or total>64*1024*1024*1024:
                raise ValueError('source needs an ETag and must be at most 64 GiB')
            with tifffile.TiffFile(io.BytesIO(header)) as image:
                page = image.pages[0]
                if not page.is_tiled or page.samplesperpixel != 1 or len(page.shape) != 2:
                    raise ValueError('source needs a tiled single-band COG')
                offsets,counts = tuple(page.dataoffsets),tuple(page.databytecounts)
                tile_h,tile_w = page.tilelength,page.tilewidth
                height,width = page.shape
            with partial.open('wb') as file:
                file.write(header)
                file.truncate(total)
            with rasterio.open(partial) as dataset:
                if dataset.crs is None:
                    raise ValueError('source needs a lunar projected CRS')
                crs = CRS.from_wkt(dataset.crs.to_wkt())
                transform = Transformer.from_crs(crs.geodetic_crs,crs,always_xy=True)
                x,y = transform.transform(longitude,latitude)
                extent = radius_m*1.1+2*math.hypot(*dataset.res)
                window = from_bounds(x-extent,y-extent,x+extent,y+extent,dataset.transform)
                first_row,first_col = math.floor(window.row_off),math.floor(window.col_off)
                last_row = math.ceil(window.row_off+window.height)
                last_col = math.ceil(window.col_off+window.width)
                if first_row < 0 or first_col < 0 or last_row > height or last_col > width:
                    raise ValueError('source does not cover the complete subset window')
            tiles_per_row = math.ceil(width/tile_w)
            tile_rows=math.ceil(last_row/tile_h)-first_row//tile_h
            tile_cols=math.ceil(last_col/tile_w)-first_col//tile_w
            if tile_rows*tile_cols>512:
                raise ValueError('subset exceeds the 512-tile download limit')
            tiles = [row*tiles_per_row+col
                     for row in range(first_row//tile_h,math.ceil(last_row/tile_h))
                     for col in range(first_col//tile_w,math.ceil(last_col/tile_w))]
            if len(tiles) > 512 or sum(counts[tile] for tile in tiles) > 256*1024*1024:
                raise ValueError('subset exceeds the 512-tile/256 MiB download limit')
            hashes = {}
            def read_tile(tile):
                start,length=offsets[tile],counts[tile]
                if length <= 0 or start < 0 or start+length > total:
                    raise ValueError('source has an invalid tile range')
                data,_,_ = _range(client,source_url,start,start+length-1,total,etag)
                return tile,data
            with partial.open('r+b') as file, ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(read_tile,tile) for tile in tiles]
                for future in as_completed(futures):
                    tile,data = future.result()
                    file.seek(offsets[tile]);file.write(data)
                    hashes[tile]=hashlib.sha256(data).hexdigest()
            partial.replace(output)
            provenance={'source':source_url,'source_etag':etag,'original_file_bytes':total,
                    'retrieved_header_sha256':hashlib.sha256(header).hexdigest(),
                    'retrieved_tile_count':len(tiles),'retrieved_tile_bytes':sum(counts[t] for t in tiles),
                    'tile_hashes':{str(tile):hashes[tile] for tile in sorted(tiles)},
                    'coverage':'only the requested polar preprocessing window is verified'}
            provenance['retrieved_subset_sha256']=subset_digest(provenance)
            return provenance
    finally:
        partial.unlink(missing_ok=True)
