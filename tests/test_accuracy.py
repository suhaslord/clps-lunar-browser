"""Independent checks of terrain coverage and measured-control comparisons."""
import json
import math

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient

from backend.app import app
from backend.terrain import global_dem as dem_module
from backend.terrain.global_dem import RADIUS_M, build_global_profile
from backend.terrain.horizon import HorizonError, horizon_at, load_coordinate_profile, validate_profile
from backend.terrain.preprocess import build_profile, sample_projected_height
from backend.terrain.validate_accuracy import compare_control_points
from tests.test_terrain import make_dem, SITE, SOURCE


def test_nearby_ridge_is_no_longer_discarded_as_two_pixels():
    grid = np.full((1800, 3600), 20000, dtype=np.uint16)
    grid[900, 1801] = 21000
    old = build_global_profile(grid, -.05, .05)
    pixel = math.pi * RADIUS_M / grid.shape[0]
    improved = build_global_profile(grid, -.05, .05, min_distance_m=pixel/math.sqrt(2))
    assert horizon_at(old, 90) < 0
    assert horizon_at(improved, 90) > 5


def test_distant_ridge_beyond_original_40km_changes_horizon():
    grid = np.full((1800, 3600), 20000, dtype=np.uint16)
    # 33 equatorial cells east, about 100 km, beyond the former search.
    grid[900, 1833] = 28000
    old = build_global_profile(grid, -.05, .05)
    improved = build_global_profile(grid, -.05, .05, max_distance_m=300000)
    assert horizon_at(old, 90) < 0
    assert horizon_at(improved, 90) > .5


def test_outer_terrain_uses_detailed_observer_height():
    grid = np.full((1800, 3600), 20000, dtype=np.uint16)
    low = build_global_profile(grid, 0, 0, 300000, 5, min_distance_m=40000, site_height_m=-1000)
    high = build_global_profile(grid, 0, 0, 300000, 5, min_distance_m=40000, site_height_m=1000)
    assert all(left > right for left, right in zip(low['horizon'], high['horizon']))
    assert high['site_elevation_m'] == 1000


def test_projected_observer_interpolates_an_analytic_height_plane(tmp_path):
    path = tmp_path/'plane.tif'
    make_dem(path)
    with rasterio.open(path,'r+') as dataset:
        rows, cols = np.indices((201,201))
        dataset.write((2*rows+3*cols).astype('float32'),1)
        x,y = dataset.transform.c + dataset.transform.a*100.75, dataset.transform.f + dataset.transform.e*101.25
        assert sample_projected_height(dataset,x,y) == pytest.approx(2*100.75+3*100.25)
        x,y = dataset.transform.c + dataset.transform.a*100.5, dataset.transform.f + dataset.transform.e*100.5
        values = dataset.read(1)
        values[101,101] = np.nan
        dataset.write(values,1)
        assert sample_projected_height(dataset,x,y) == pytest.approx(500)


def test_native_pixel_footprint_replaces_fixed_160m_exclusion(tmp_path):
    path = tmp_path/'nearby.tif'
    make_dem(path, [(90,100,100)])
    old = build_profile(str(path),SITE,SOURCE,2500,10,2,160)
    improved = build_profile(str(path),SITE,SOURCE,2500,10,2)
    assert improved['min_distance_m'] == pytest.approx(math.sqrt(2)*50)
    assert horizon_at(improved,90) > horizon_at(old,90)+10


def test_precise_coordinate_profiles_are_exact_and_ambiguity_fails(tmp_path):
    path = tmp_path/'terrain.tif'
    make_dem(path)
    profile = build_profile(str(path),SITE,SOURCE,2500,10)
    first = tmp_path/'coordinate-custom.json'
    first.write_text(json.dumps(profile))
    loaded = load_coordinate_profile(SITE['latitude'],SITE['longitude'],tmp_path)
    loaded['horizon'][0] = 80
    assert load_coordinate_profile(SITE['latitude'],SITE['longitude'],tmp_path)['horizon'][0] != 80
    assert load_coordinate_profile(SITE['latitude']+1e-8,SITE['longitude'],tmp_path) is None
    (tmp_path/'coordinate-duplicate.json').write_text(json.dumps(profile))
    with pytest.raises(HorizonError,match='multiple'):
        load_coordinate_profile(SITE['latitude'],SITE['longitude'],tmp_path)


@pytest.mark.parametrize('field,value', [('min_distance_m',-1),('min_distance_m',True),
                                        ('min_distance_m',float('nan')),('pixel_resolution_m',0),
                                        ('pixel_resolution_m','20'),('datum_radius_m',6371000)])
def test_bad_coverage_metadata_cannot_claim_lunar_accuracy(tmp_path,field,value):
    path=tmp_path/'terrain.tif'; make_dem(path)
    profile=build_profile(str(path),SITE,SOURCE,2500,10)
    profile[field]=value
    with pytest.raises(HorizonError): validate_profile(profile)


def test_far_ceiling_bounds_independent_spherical_rays(monkeypatch):
    grid = np.full((1800,3600), 28000, dtype=np.uint16)
    monkeypatch.setattr(dem_module,'global_dem',lambda:(grid,('synthetic',)))
    monkeypatch.setattr(dem_module,'_height_ceiling',lambda _:4000.25)
    rng=np.random.default_rng(781)
    for elevation in [-9000,0,10757]:
        profile={'site_elevation_m':elevation,'observer_height_m':2,'max_distance_m':300000}
        ceiling=dem_module.distant_terrain_ceiling(profile)
        for distance,height in zip(rng.uniform(300000,math.pi*RADIUS_M,100),rng.uniform(-9000,4000,100)):
            theta=distance/RADIUS_M
            observer=np.array([RADIUS_M+elevation+2,0.,0.])
            cell=np.array([(RADIUS_M+height)*math.cos(theta),(RADIUS_M+height)*math.sin(theta),0.])
            ray=cell-observer
            independent=math.degrees(math.atan2(ray[0],math.hypot(ray[1],ray[2])))
            assert independent <= ceiling+1e-9


def test_uncertainty_metadata_does_not_turn_a_model_into_a_certificate():
    client=TestClient(app)
    params={'lat':0,'lon':0,'time':'2026-10-15T00:00:00Z'}
    from backend.terrain.global_dem import dem_path
    if not dem_path().is_file(): pytest.skip('real DEM not installed')
    result=client.get('/api/visibility',params=params)
    assert result.status_code==200
    payload=result.json()
    accuracy=payload['terrain']['accuracy']
    assert accuracy['survey_grade'] is False
    assert accuracy['horizon_error_deg'] is None
    assert payload['terrain']['max_distance_m']==300000
    assert payload['terrain']['distant_raster_bounded'] is True
    for body in ['sun','earth']:
        assert payload[body]['visibility_validation']=='unvalidated'
        assert payload[body]['terrain_clearance_deg']==pytest.approx(payload[body]['elevation']-payload[body]['terrain_horizon'])


def controls():
    return [{'feature_id':str(i),'model_latitude':0.,'model_longitude':lon,
             'reference_latitude':0.,'reference_longitude':lon,
             'reference_elevation_m':height}
            for i,(lon,height) in enumerate([(180,100),(-180,102),(0,97)])]


def test_control_statistics_match_independent_residual_arithmetic():
    points=controls()
    points[0]['reference_longitude']=-180
    report=compare_control_points(points,lambda *_:100,1,2)
    assert report['horizontal_max_observed_m']<1e-8
    assert report['vertical_bias_m']==pytest.approx(1/3)
    assert report['vertical_rmse_m']==pytest.approx(math.sqrt(13/3))
    assert report['vertical_max_absolute_observed_m']==3
    assert report['all_observed_points_within_tolerances'] is False
    assert report['survey_grade'] is False
    passing=compare_control_points(points,lambda *_:100,1,3)
    assert passing['all_observed_points_within_tolerances'] is True
    assert passing['survey_grade'] is False


def test_control_horizontal_distance_uses_matched_positions():
    points=controls()
    points[2]['reference_longitude']=math.degrees(10/RADIUS_M)
    report=compare_control_points(points,lambda *_:100,9,5)
    assert report['horizontal_max_observed_m']==pytest.approx(10)
    assert report['all_observed_points_within_tolerances'] is False


@pytest.mark.parametrize('bad',[True,'1',float('nan'),float('inf'),10**1000])
def test_control_comparison_rejects_unusable_measurements(bad):
    points=controls();points[0]['reference_elevation_m']=bad
    with pytest.raises(ValueError):compare_control_points(points,lambda *_:100,1,3)


def test_control_ids_and_tolerances_are_not_silently_coerced():
    points=controls();points[1]['feature_id']=points[0]['feature_id']
    with pytest.raises(ValueError,match='unique'):compare_control_points(points,lambda *_:100,1,3)
    with pytest.raises(ValueError):compare_control_points(controls(),lambda *_:100,0,3)
    with pytest.raises(ValueError):compare_control_points(controls()[:1],lambda *_:100,1,3)


def test_missing_required_site_profile_is_not_a_coarse_fallback(monkeypatch,tmp_path):
    monkeypatch.setattr('backend.terrain.horizon.PROFILE_DIR',tmp_path)
    for name in ['athena-im2','odysseus-im1']:
        response=TestClient(app).get(f'/api/sites/{name}/horizon')
        assert response.status_code==503
        assert 'Detailed terrain profile' in response.json()['detail']


def test_failed_profile_publication_preserves_old_file(monkeypatch,tmp_path):
    import backend.terrain.preprocess as module
    path=tmp_path/'source.tif';make_dem(path)
    profile=build_profile(str(path),SITE,SOURCE,2500,10)
    output=tmp_path/'profile.json'
    module.write_profile(output,profile)
    original=output.read_bytes()
    def fail(*_):raise OSError('simulated interrupted publication')
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError):module.write_profile(output,{**profile,'horizon':[5]*36})
    assert output.read_bytes()==original
    assert not list(tmp_path.glob('*.tmp'))


def test_reduced_inner_radius_matches_full_globe_cartesian_oracle():
    from tests.test_deep_geometry import _full_globe_reference
    rng=np.random.default_rng(927)
    grid=rng.integers(16000,28000,size=(180,360),dtype=np.uint16)
    pixel=math.pi*RADIUS_M/grid.shape[0]
    positions=[(90,37),(-90,-150),(0,180),(0,-180)]
    positions+=list(zip(rng.uniform(-90,90,8),rng.uniform(-180,180,8)))
    for lat,lon in positions:
        profile=build_global_profile(grid,lat,lon,250000,10,min_distance_m=pixel/math.sqrt(2))
        assert profile['horizon']==pytest.approx(_full_globe_reference(grid,lat,lon,profile),abs=.000051)


@pytest.mark.parametrize('invalid',[None,{}, {'source_etag':'v1','coverage':'window only','retrieved_subset_sha256':'invalid'}])
def test_bad_subset_provenance_is_unavailable_instead_of_a_server_crash(tmp_path,invalid):
    path=tmp_path/'terrain.tif';make_dem(path)
    profile=build_profile(str(path),SITE,SOURCE,2500,10)
    profile['source_subset']=invalid
    with pytest.raises(HorizonError,match='subset provenance'):validate_profile(profile)
