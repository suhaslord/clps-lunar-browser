"""Byte integrity and bounded transfers for native lunar COG preprocessing."""
import re
from pathlib import Path

import httpx
import numpy as np
import pytest
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from backend.terrain.fetch_window import _range, fetch_window, subset_digest
from backend.terrain.preprocess import build_profile

URL='https://example.org/lunar.tif'
SITE={'id':'test-site','latitude':-84.79,'longitude':29.2}


def test_partial_byte_response_retries_then_recovers():
    calls=[]
    def handler(request):
        calls.append(request)
        data=b'abc' if len(calls)<3 else b'abcd'
        return httpx.Response(206,headers={'Content-Range':'bytes 4-7/20','ETag':'v1'},content=data)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data,total,etag=_range(client,URL,4,7,20,'v1')
    assert (data,total,etag)==(b'abcd',20,'v1')
    assert len(calls)==3


@pytest.mark.parametrize('headers,body',[({'Content-Range':'bytes 0-3/20','ETag':'v1'},b'abcd'),
                                         ({'Content-Range':'bytes 4-7/21','ETag':'v1'},b'abcd'),
                                         ({'Content-Range':'bytes 4-7/20','ETag':'v2'},b'abcd'),
                                         ({'Content-Range':'bytes 4-7/20','ETag':'v1'},b'abcde')])
def test_bad_ranges_changed_source_and_oversized_payload_are_rejected(headers,body):
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(206,headers=headers,content=body))) as client:
        with pytest.raises(ValueError):_range(client,URL,4,7,20,'v1')


def test_ignored_range_never_reads_a_whole_source_file():
    class UnreadableWholeFile(httpx.SyncByteStream):
        def __iter__(self):raise AssertionError('whole source body must not be read')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,stream=UnreadableWholeFile()))) as client:
        with pytest.raises(ValueError,match='byte-range'):_range(client,URL,0,1023)
        with pytest.raises(ValueError,match='oversized'):_range(client,URL,0,10*1024*1024)


def test_cog_subset_preserves_native_pixels_georeferencing_and_profile(monkeypatch,tmp_path):
    crs=CRS.from_proj4('+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m')
    x,y=Transformer.from_crs(crs.geodetic_crs,crs,always_xy=True).transform(SITE['longitude'],SITE['latitude'])
    source=tmp_path/'complete.tif'
    rows,cols=np.indices((201,201));values=(rows*2+cols*3).astype('float32')
    with rasterio.open(source,'w',driver='GTiff',height=201,width=201,count=1,dtype='float32',
                       crs=crs.to_wkt(),transform=from_origin(x-10050,y+10050,100,100),
                       tiled=True,blockxsize=32,blockysize=32,compress='deflate') as dataset:
        dataset.write(values,1)
    content=source.read_bytes()
    def handler(request):
        first,last=map(int,re.fullmatch(r'bytes=(\d+)-(\d+)',request.headers['Range']).groups())
        last=min(last,len(content)-1)
        return httpx.Response(206,headers={'Content-Range':f'bytes {first}-{last}/{len(content)}','ETag':'stable-source'},
                              content=content[first:last+1])
    original_client=httpx.Client
    monkeypatch.setattr('backend.terrain.fetch_window.httpx.Client',lambda **kwargs:original_client(
        **kwargs,transport=httpx.MockTransport(handler)))
    output=tmp_path/'local-window.tif'
    provenance=fetch_window(URL,SITE['latitude'],SITE['longitude'],2500,output)
    assert provenance['retrieved_subset_sha256']==subset_digest(provenance)
    assert provenance['source_etag']=='stable-source'
    assert provenance['retrieved_tile_count']>0
    original=build_profile(str(source),SITE,URL,2500,10)
    reconstructed=build_profile(str(output),SITE,URL,2500,10)
    assert reconstructed==original
    assert not list(tmp_path.glob('*.partial.tif'))


def test_failed_fetch_preserves_previously_published_subset(monkeypatch,tmp_path):
    output=tmp_path/'window.tif';output.write_bytes(b'previous verified window')
    original_client=httpx.Client
    monkeypatch.setattr('backend.terrain.fetch_window.httpx.Client',lambda **kwargs:original_client(
        **kwargs,transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'ignored range'))))
    with pytest.raises(ValueError):fetch_window(URL,-85,30,40000,output)
    assert output.read_bytes()==b'previous verified window'
    assert not list(tmp_path.glob('*.partial.tif'))
