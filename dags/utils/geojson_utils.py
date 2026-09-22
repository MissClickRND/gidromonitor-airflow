import json
import ee


ALLOWED_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}


def normalize_geojson(polygon):
    if isinstance(polygon, str):
        polygon = json.loads(polygon)

    if not isinstance(polygon, dict):
        raise ValueError("polygon must be a GeoJSON dict or JSON string")

    geojson_type = polygon.get("type")

    if geojson_type == "FeatureCollection":
        features = polygon.get("features") or []
        if not features:
            raise ValueError("FeatureCollection is empty")
        geometry = features[0].get("geometry")

    elif geojson_type == "Feature":
        geometry = polygon.get("geometry")

    else:
        geometry = polygon

    if not isinstance(geometry, dict):
        raise ValueError("GeoJSON geometry not found")

    if geometry.get("type") not in ALLOWED_GEOMETRY_TYPES:
        raise ValueError(
            f"Expected Polygon or MultiPolygon, got: {geometry.get('type')}"
        )

    if "coordinates" not in geometry:
        raise ValueError("GeoJSON geometry has no coordinates")

    return geometry


def geojson_to_ee_geometry(polygon):
    if isinstance(polygon, ee.Geometry):
        return polygon
        
    if isinstance(polygon, list) and len(polygon) > 0 and isinstance(polygon[0], list):
         if isinstance(polygon[0][0], (int, float)):
             polygon = [polygon]
         polygon = {"type": "Polygon", "coordinates": polygon}
         
    geometry = normalize_geojson(polygon)

    geom_type = geometry["type"]
    coordinates = geometry["coordinates"]

    if geom_type == "Polygon":
        return ee.Geometry.Polygon(coordinates)

    if geom_type == "MultiPolygon":
        return ee.Geometry.MultiPolygon(coordinates)

    return ee.Geometry(geometry)