"""Unit tests for map↔client affine projection and radar helpers."""

from __future__ import annotations

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.map_projection import (
    MapClientSample,
    belief_to_radar_norm,
    calibrate_affine,
    detect_radar_frustum_map_aabb,
    map_point_near_client,
    map_to_client,
    radar_norm_to_map,
    transform_from_army_anchor,
    transform_from_view_aabb,
)


def test_calibrate_recovers_exact_affine():
    # x_c = 0.02*x_m + 0.1; y_c = -0.02*y_m + 0.9
    samples = [
        MapClientSample(client_xy=(0.30, 0.50), map_xy=(10.0, 20.0)),
        MapClientSample(client_xy=(0.50, 0.30), map_xy=(20.0, 30.0)),
        MapClientSample(client_xy=(0.70, 0.70), map_xy=(30.0, 10.0)),
        MapClientSample(client_xy=(0.40, 0.40), map_xy=(15.0, 25.0)),
    ]
    # Build samples from a known transform so recovery is exact.
    known = (
        (0.02, 0.0, 0.10),
        (0.0, -0.02, 0.90),
    )

    def apply(m, xy):
        (a, b, c), (d, e, f) = m
        x, y = xy
        return (a * x + b * y + c, d * x + e * y + f)

    samples = [
        MapClientSample(client_xy=apply(known, m), map_xy=m)
        for m in ((10.0, 20.0), (20.0, 30.0), (30.0, 10.0), (15.0, 25.0))
    ]
    fit = calibrate_affine(samples)
    assert fit is not None
    assert fit.residual_rms < 1e-9
    for s in samples:
        px, py = fit.map_to_client(s.map_xy)
        assert abs(px - s.client_xy[0]) < 1e-6
        assert abs(py - s.client_xy[1]) < 1e-6
    back = fit.client_to_map(samples[0].client_xy)
    assert back is not None
    assert abs(back[0] - samples[0].map_xy[0]) < 1e-6


def test_calibrate_rejects_underdetermined():
    assert calibrate_affine([]) is None
    assert (
        calibrate_affine(
            [MapClientSample(client_xy=(0.5, 0.5), map_xy=(1.0, 1.0))]
        )
        is None
    )


def test_map_to_client_rejects_outside_viewport():
    t = transform_from_army_anchor(army_map_xy=(100.0, 100.0), scale=0.05)
    assert map_to_client(t, (100.0, 100.0)) is not None
    # Far east → past right viewport edge.
    assert map_to_client(t, (400.0, 100.0)) is None


def test_view_aabb_and_army_anchor_project_consistently():
    aabb = transform_from_view_aabb(
        map_min=(80.0, 70.0),
        map_max=(100.0, 90.0),
        client_bounds=(0.1, 0.1, 0.9, 0.9),
    )
    assert aabb is not None
    # Centre of AABB → centre of client bounds.
    cx, cy = aabb.map_to_client((90.0, 80.0))
    assert abs(cx - 0.5) < 1e-6
    assert abs(cy - 0.5) < 1e-6
    # North of centre → smaller client Y.
    assert aabb.map_to_client((90.0, 85.0))[1] < cy

    anchor = transform_from_army_anchor(army_map_xy=(89.0, 82.0), scale=0.01)
    assert map_point_near_client(anchor, (89.0, 82.0))
    segesta = map_to_client(anchor, (83.0, 84.0))
    assert segesta is not None
    assert segesta[0] < 0.50  # west of Flavius


def test_belief_radar_roundtrip():
    radar = belief_to_radar_norm((100.0, 75.0), map_bounds=(0.0, 0.0, 200.0, 150.0))
    back = radar_norm_to_map(radar, map_bounds=(0.0, 0.0, 200.0, 150.0))
    assert abs(back[0] - 100.0) < 0.5
    assert abs(back[1] - 75.0) < 0.5


def test_detect_radar_frustum_map_aabb():
    # Synthetic frame: red box inside the radar region.
    w, h = 1000, 1000
    img = Image.new("RGB", (w, h), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    # Default radar roughly (0.879, 0.055)–(0.998, 0.185)
    draw.rectangle(
        (900, 80, 980, 150),
        outline=(220, 40, 40),
        width=3,
    )
    aabb = detect_radar_frustum_map_aabb(img, map_bounds=(0.0, 0.0, 200.0, 150.0))
    assert aabb is not None
    (min_x, min_y), (max_x, max_y) = aabb
    assert max_x > min_x and max_y > min_y
