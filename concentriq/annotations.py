#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

"""concentriq.annotations

functions to convert between QuPath-like geojson annotations and
Proscia-Concentriq-style annotations

"""
from __future__ import annotations

import struct
from typing import Any

from shapely.geometry import Polygon

from concentriq.models import Annotation
from concentriq.models import Image


def proscia_from_geojson(
    geojson: dict[str, Any],
    image: Image,
    *,
    shapely_fix_in_viewport_coords: bool = False,
) -> Annotation:
    """make a proscia annotation from geojson"""
    image_id = image.id
    # proscia annotations are in viewport coordinates
    scale_px_to_vp = 10000.0 / image.img_width
    geometry = geojson["geometry"]
    properties = geojson["properties"]
    type_ = geometry["type"]
    if type_ == "Polygon":
        _shape = "free"
        shape_string = " ".join(
            f"{x * scale_px_to_vp:f},{y * scale_px_to_vp:f}"
            for x, y in geometry["coordinates"][0]
        )

        if shapely_fix_in_viewport_coords:
            p = Polygon([list(map(float, x.split(","))) for x in shape_string.split()])
            if not p.is_valid:
                p = p.buffer(0, 1)
                if not p.is_valid:
                    p = p.buffer(0, 1)
                    if not p.is_valid:
                        raise ValueError("invalid geometry")
                shape_string = " ".join(f"{x:f},{y:f}" for x, y in p.exterior.coords)

        capture_bounds = "0.0 0.0 10000.0 10000.0"
    else:
        raise NotImplementedError(f"haven't gotten to {type_!r} yet...")

    _c = properties.get("classification", {}).get("colorRGB", -3670016)
    _, r, g, b = struct.pack(">i", _c)

    return Annotation(
        text=properties.get("classification", {}).get("name", ""),
        shape=_shape,
        shape_string=shape_string,
        capture_bounds=capture_bounds,
        image_id=image_id,
        color=f"#{bytes([r, g, b]).hex()}",
        is_negative=False,
        is_segmenting=False,
    )


def proscia_to_geojson(annotation: Annotation, image: Image) -> dict[str, Any]:
    """convert a proscia annotation to geojson"""
    # proscia coordinates are in viewport coordinates
    scale_vp_to_px = image.img_width / 10000.0
    if annotation.shape == "free":
        type_ = "Polygon"
        coordinates = [
            [
                list(map(lambda x: float(x) * scale_vp_to_px, pt.split(",")))
                for pt in annotation.shape_string.split()
            ]
        ]
    else:
        raise NotImplementedError(f"haven't gotten to {annotation.shape!r} yet...")

    assert "#" == annotation.color[0] and len(annotation.color) == 7
    r = int(annotation.color[1:3], 16)
    g = int(annotation.color[3:5], 16)
    b = int(annotation.color[5:7], 16)
    color = struct.unpack(">i", bytes([255, r, g, b]))

    return {
        "type": "Feature",
        "id": "PathAnnotationObject",
        "geometry": {
            "type": type_,
            "coordinates": coordinates,
        },
        "properties": {
            "classification": {
                "name": annotation.text,
                "colorRGB": color,
            },
            "isLocked": False,
            "measurements": [],
        },
    }
