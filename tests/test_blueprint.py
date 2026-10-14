"""Provjera logike podsjetnika iz blueprinta (bez dizanja automatizacije).

Renderira `due_window` predložak iz blueprinta pravim HA template engineom i
provjerava kada podsjetnik stigne. Pokreće se u HA okruženju:

    .venv-ha/bin/pytest tests/test_blueprint.py
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

BLUEPRINT = (
    Path(__file__).resolve().parent.parent
    / "blueprints"
    / "automation"
    / "knjiznica_metelgrad"
    / "podsjetnik_rok_vracanja.yaml"
)

LOANS_ENTITY = "sensor.ana_posudbe"


class _Loader(yaml.SafeLoader):
    """YAML loader koji `!input` polja pretvara u običnu oznaku."""


def _input_tag(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return f"!input:{loader.construct_scalar(node)}"


_Loader.add_constructor("!input", _input_tag)

BLUEPRINT_DOC: dict[str, Any] = yaml.load(BLUEPRINT.read_text(encoding="utf-8"), Loader=_Loader)


def _set_loans(hass: HomeAssistant, *offsets: int) -> None:
    """Postavi posudbe s rokom `danas + offset` dana."""
    today = dt_util.now().date()
    hass.states.async_set(
        LOANS_ENTITY,
        str(len(offsets)),
        {
            "loans": [
                {"title": f"rok{offset:+d}", "due_on": (today + timedelta(days=offset)).isoformat()}
                for offset in offsets
            ]
        },
    )


def _window(hass: HomeAssistant, days_before: int, repeat_daily: bool) -> Any:
    return Template(BLUEPRINT_DOC["variables"]["due_window"], hass).async_render(
        {
            "loans_entity": LOANS_ENTITY,
            "days_before": days_before,
            "repeat_daily": repeat_daily,
        }
    )


def _titles(hass: HomeAssistant, days_before: int, repeat_daily: bool) -> list[str]:
    window = _window(hass, days_before, repeat_daily)
    # Ključno: ako predložak vrati tekst umjesto popisa, `| count` u uvjetu
    # automatizacije broji znakove i notifikacija stiže uvijek.
    assert isinstance(window, list), f"due_window nije popis nego {type(window)}"
    return [loan["title"] for loan in window]


def test_repeat_daily_notifies_every_day_in_window(hass: HomeAssistant) -> None:
    _set_loans(hass, -1, 0, 3, 4)
    # Prozor je [danas, danas+3]; rok koji je prošao se ne javlja.
    assert _titles(hass, 3, True) == ["rok+0", "rok+3"]
    assert _titles(hass, 10, True) == ["rok+0", "rok+3", "rok+4"]


def test_single_reminder_only_on_the_exact_day(hass: HomeAssistant) -> None:
    _set_loans(hass, -1, 0, 3, 4)
    # Bez ponavljanja: samo knjiga kojoj je rok točno danas+3.
    assert _titles(hass, 3, False) == ["rok+3"]
    # "rok+3" je u prozoru samo jedan dan - dan prije prozor gleda danas+4.
    assert _titles(hass, 4, False) == ["rok+4"]


def test_window_is_empty_without_loans(hass: HomeAssistant) -> None:
    hass.states.async_set(LOANS_ENTITY, "0", {})
    assert _window(hass, 3, True) == []
    assert _window(hass, 3, False) == []


def test_condition_and_message_work_with_the_window(hass: HomeAssistant) -> None:
    """Uvjet i poruka iz blueprinta moraju raditi s istim popisom."""
    _set_loans(hass, 0, 3)
    blueprint = BLUEPRINT_DOC
    variables = {
        "loans_entity": LOANS_ENTITY,
        "days_before": 3,
        "repeat_daily": True,
    }
    due_window = Template(blueprint["variables"]["due_window"], hass).async_render(variables)
    variables["due_window"] = due_window

    condition = blueprint["conditions"][0]["value_template"]
    assert Template(condition, hass).async_render(variables) is True

    message = blueprint["actions"][0]["data"]["message"]
    rendered = Template(message, hass).async_render(variables)
    assert "rok+0" in rendered and "rok+3" in rendered


def test_blueprint_structure_is_sane() -> None:
    blueprint = BLUEPRINT_DOC
    assert blueprint["triggers"][0]["trigger"] == "time"
    assert blueprint["conditions"][0]["condition"] == "template"
    assert set(blueprint["blueprint"]["input"]) == {
        "loans_entity",
        "days_before",
        "repeat_daily",
        "notify_time",
        "notify_service",
        "notify_title",
    }
