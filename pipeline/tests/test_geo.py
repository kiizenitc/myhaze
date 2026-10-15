import pytest

from myhaze.geo import bearing_deg, haversine_km, region_of


@pytest.mark.parametrize("name,lat,lon,region", [
    ("Dumai, Riau", 1.67, 101.45, "sumatra"),
    ("Jambi", -1.6, 103.6, "sumatra"),
    ("Banda Aceh", 5.55, 95.32, "sumatra"),
    ("Klang", 3.04, 101.45, "peninsular"),
    ("Port Dickson", 2.52, 101.80, "peninsular"),
    ("Penang", 5.41, 100.33, "peninsular"),
    ("Palangkaraya", -2.21, 113.92, "kalimantan"),
    ("Pontianak", -0.03, 109.33, "kalimantan"),
    ("Kuching", 1.55, 110.35, "my_borneo"),
    ("Tawau", 4.25, 117.89, "my_borneo"),
    ("Manila", 14.6, 121.0, "other"),
])
def test_region_of_places(name, lat, lon, region):
    assert region_of(lat, lon) == region, name


def test_bearing_and_distance():
    assert bearing_deg(0, 100, 1, 100) == pytest.approx(0, abs=0.01)    # due north
    assert bearing_deg(0, 100, 0, 101) == pytest.approx(90, abs=0.01)   # due east
    assert bearing_deg(3, 101, 2, 100) == pytest.approx(225, abs=0.5)   # south-west
    assert haversine_km(0, 100, 1, 100) == pytest.approx(111.2, abs=0.2)
