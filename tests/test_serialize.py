from trendforge.domain.catalog import model_catalog, option_by_id
from trendforge.domain.enums import BackendKind, ContentFormat, VideoStyle, LengthPreset
from trendforge.domain.models import GenerationRequest
from trendforge.domain.serialize import dumps, project_from_dict, request_from_dict
from trendforge.domain.models import Project
import json


def test_catalog_auto_and_quick():
    ids = {m.id for m in model_catalog()}
    assert "auto" in ids
    assert "quick_explainer" in ids
    assert "maestro_director" in ids
    quick = option_by_id("quick_explainer")
    assert quick and quick.fits(0)


def test_request_roundtrip():
    req = GenerationRequest(
        topic="hello",
        style=VideoStyle.DOCUMENTARY,
        length=LengthPreset.LONG,
        content_format=ContentFormat.DOCUSERIES,
        channel_name="Signal Cut",
        series_title="Investigations",
        episode_index=3,
    )
    data = json.loads(dumps(req))
    back = request_from_dict(data)
    assert back.topic == "hello"
    assert back.style is VideoStyle.DOCUMENTARY
    assert back.length is LengthPreset.LONG
    assert back.content_format is ContentFormat.DOCUSERIES
    assert back.channel_name == "Signal Cut"
    assert back.episode_index == 3


def test_project_roundtrip():
    req = GenerationRequest(topic="x")
    project = Project.create("x", req, folder="C:/tmp")
    data = json.loads(dumps(project))
    back = project_from_dict(data)
    assert back.title == "x"
    assert back.request.topic == "x"
    assert back.request.backend is BackendKind.AUTO
