"""Unit tests for view compositor budgets."""

from PIL import Image

from comstar_game_ai.agent.compositor.views import (
    MAX_TOTAL_BYTES,
    ViewBudget,
    compose_canvas,
    compose_reach_images,
)


def test_compose_reach_images_respects_budget():
    views = [Image.new("RGB", (1920, 1080), color=(i * 20, 40, 60)) for i in range(8)]
    budget = ViewBudget(max_images=4, max_total_bytes=MAX_TOTAL_BYTES)
    images, stats = compose_reach_images(views, budget)
    assert len(images) <= 4
    assert stats["encoded"] == len(images)
    total = sum(len(img["dataBase64"]) for img in images)
    assert total > 0
    for img in images:
        assert img["mimeType"] == "image/jpeg"
        assert img["name"].startswith("view_")


def test_compose_canvas_layers():
    base = Image.new("RGB", (100, 100), color=(255, 0, 0))
    overlay = Image.new("RGB", (50, 50), color=(0, 255, 0))
    from comstar_game_ai.agent.compositor.views import ViewLayer

    canvas = compose_canvas([ViewLayer(image=base), ViewLayer(image=overlay, box=(10, 10, 60, 60))])
    assert canvas.size == (1280, 720)
