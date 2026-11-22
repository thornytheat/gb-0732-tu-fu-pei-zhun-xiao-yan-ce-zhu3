import math

from app.config import LOCAL_RADIUS_M
from app.modules.coordinates.numbers import clean, failure, measure, normalized_unit

WGS84_A = 6_378_137.0
WGS84_E2 = 6.6943799901413165e-3


def ecef(longitude, latitude):
    lon, lat = map(math.radians, (longitude, latitude))
    radius = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    return (radius * math.cos(lat) * math.cos(lon), radius * math.cos(lat) * math.sin(lon),
            radius * (1 - WGS84_E2) * math.sin(lat))


def to_enu(longitude, latitude, origin):
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise failure('COORDINATE_RANGE')
    x, y, z = (point - base for point, base in zip(ecef(longitude, latitude), ecef(*origin)))
    lon, lat = map(math.radians, origin)
    east = -math.sin(lon) * x + math.cos(lon) * y
    north = -math.sin(lat) * (math.cos(lon) * x + math.sin(lon) * y) + math.cos(lat) * z
    # ENU 平面投影会把地球另一侧也投到原点附近，工作区用三维弦长约束。
    if math.hypot(x, y, z) > LOCAL_RADIUS_M:
        raise failure('COORDINATE_RANGE')
    return east, north


def ground_position(row, origin):
    crs = clean(row['crs']).upper()
    unit = normalized_unit(row['unit'])
    if crs == 'WGS84':
        if unit != 'deg':
            raise failure('UNIT_MISMATCH')
        longitude, latitude = (measure(row[key], unit) for key in ('x', 'y'))
        return to_enu(longitude, latitude, origin)
    if crs != 'LOCAL-ENU':
        raise failure('INVALID_CRS')
    if unit not in {'m', 'cm'}:
        raise failure('UNIT_MISMATCH')
    divisor = 100 if unit == 'cm' else 1
    east, north = (measure(row[key], unit) / divisor for key in ('x', 'y'))
    if math.hypot(east, north) > LOCAL_RADIUS_M:
        raise failure('COORDINATE_RANGE')
    return east, north


def pixel_position(u, v, sheet):
    u, v = measure(u, 'px'), measure(v, 'px')
    if not (0 <= u <= sheet['width_px'] and 0 <= v <= sheet['height_px']):
        raise failure('COORDINATE_RANGE')
    return u, v
