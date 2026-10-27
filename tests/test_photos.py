import os

from app import photos


def put(folder, name, mtime=1_700_000_000):
    p = folder / name
    p.write_bytes(b"\xff\xd8\xff")
    os.utime(p, (mtime, mtime))
    return p


def test_list_photos_filters_and_sorts(tmp_path):
    put(tmp_path, "b-2.jpg", 1_700_000_100)
    put(tmp_path, "A1.jpg")
    put(tmp_path, "x.png")
    put(tmp_path, ".tmp.jpg")
    put(tmp_path, "has space.jpg")
    (tmp_path / "sub.jpg").mkdir()
    assert photos.list_photos(tmp_path) == [{"name": "A1.jpg", "v": 1_700_000_000},
                                            {"name": "b-2.jpg", "v": 1_700_000_100}]


def test_list_photos_missing_folder(tmp_path):
    assert photos.list_photos(tmp_path / "nope") == []
    assert photos.list_photos(None) == []


def test_photo_path(tmp_path):
    put(tmp_path, "ok.jpg")
    assert photos.photo_path(tmp_path, "ok.jpg") == tmp_path / "ok.jpg"
    for bad in ("../ok.jpg", "ok.png", "missing.jpg", ".tmp.jpg", ""):
        assert photos.photo_path(tmp_path, bad) is None
    assert photos.photo_path(None, "ok.jpg") is None


def test_slideshow_hours(freeze):
    assert photos.slideshow_hours(freeze("2026-10-27T06:59")) is False
    assert photos.slideshow_hours(freeze("2026-10-27T07:00")) is True
    assert photos.slideshow_hours(freeze("2026-10-27T20:59")) is True
    assert photos.slideshow_hours(freeze("2026-10-27T21:00")) is False
    # DST ends Sun 1 Nov 2026; local wall time still decides.
    assert photos.slideshow_hours(freeze("2026-11-01T07:30")) is True
