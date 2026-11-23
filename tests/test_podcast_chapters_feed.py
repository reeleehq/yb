"""Podcast chapter documents and RSS feed output (pure XML; mutagen/feedgen tests skip when absent)."""

from datetime import datetime, timezone

import pytest
from mixing.chapters import Chapter

from yb.podcast import chapters as C

CHAPS = [Chapter(0.0, "Intro & <more>"), Chapter(61.5, "Main"), Chapter(3725.25, "Outro")]


def test_psc_time_formats_hours_minutes_seconds_millis():
    assert C._psc_time(0) == "00:00:00.000"
    assert C._psc_time(61.5) == "00:01:01.500"
    assert C._psc_time(3725.25) == "01:02:05.250"


def test_psc_xml_escapes_titles_and_lists_every_chapter():
    xml = C.psc_xml(CHAPS)
    assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>') and xml.endswith("</psc:chapters>\n")
    assert 'title="Intro &amp; &lt;more&gt;"' in xml
    assert xml.count("<psc:chapter ") == 3 and 'start="01:02:05.250"' in xml


def test_write_psc_round_trips_through_a_file(tmp_path):
    p = C.write_psc(CHAPS, tmp_path / "c.psc")
    assert p.read_text(encoding="utf-8") == C.psc_xml(CHAPS)


def test_write_id3_chapters_is_idempotent(tmp_path):
    mutagen_id3 = pytest.importorskip("mutagen.id3")
    mp3 = tmp_path / "a.mp3"
    mp3.write_bytes(b"\x00" * 64)
    C.write_id3_chapters(mp3, CHAPS, duration=4000.0)
    C.write_id3_chapters(mp3, CHAPS[:2], duration=100.0)
    tags = mutagen_id3.ID3(str(mp3))
    chaps = sorted(k for k in tags.keys() if k.startswith("CHAP"))
    assert len(chaps) == 2 and any(k.startswith("CTOC") for k in tags.keys())
    last = tags[chaps[-1]]
    assert last.start_time == 61500 and last.end_time == 100000


def test_build_feed_includes_channel_and_episode_fields():
    pytest.importorskip("feedgen")
    from yb.podcast.feed import EpisodeFeedItem, PodcastChannel, _hms, build_feed

    assert _hms(59) == "0:59" and _hms(3725) == "1:02:05"
    channel = PodcastChannel(
        title="Show", link="https://x.test", description="d", language="en",
        author="Ann", email="a@x.test", image_url="https://x.test/i.png", explicit=True,
        categories=["Technology"],
    )
    ep = EpisodeFeedItem(
        title="E1", description="first", audio_url="https://x.test/e1.mp3",
        audio_length_bytes=123, pubdate=datetime(2024, 1, 2, tzinfo=timezone.utc),
        duration_seconds=3725, image_url="https://x.test/e1.png",
    )
    xml = build_feed(channel, [ep])
    for needle in ("<title>Show</title>", "https://x.test/e1.mp3", 'length="123"', "1:02:05", "Technology", "explicit"):
        assert needle in xml
