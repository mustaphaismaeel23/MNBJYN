"""Kano State LGA and electoral ward data.

The location names are sourced from the MIT-licensed mykeels/inec-polling-units
dataset; see the accompanying license file.
"""
import json
from pathlib import Path


with Path(__file__).with_name("kano_lgas.json").open(encoding="utf-8-sig") as file:
    KANO_LGAS = [
        (item["key"], item["name"], item["wards"])
        for item in json.load(file)
    ]

LGA_NAMES = {key: name for key, name, _ in KANO_LGAS}
LGA_WARDS = {key: wards for key, _, wards in KANO_LGAS}


def lga_json_data():
    """JSON-serialisable structure for the front-end pickers."""
    return [{"key": key, "name": name, "wards": wards} for key, name, wards in KANO_LGAS]


STATE_NAME = "Kano"
STATE_CODE = "20"

LGA_KEYS = [key for key, _, _ in KANO_LGAS]
LGA_INDEX = {key: index for index, key in enumerate(LGA_KEYS)}


def normalise_name(value):
    """Lower-case a place name and drop everything except letters/digits."""
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def lga_code(key):
    """Return a state/LGA code such as '20/02'."""
    return f"{STATE_CODE}/{LGA_INDEX[key] + 1:02d}"


def ward_code(key, ward_index):
    """Return a state/LGA/ward code such as '20/02/03'."""
    return f"{lga_code(key)}/{ward_index + 1:02d}"


def pu_code(key, ward_index, number):
    """Return a state/LGA/ward/polling-unit code such as '20/02/03/007'."""
    return f"{ward_code(key, ward_index)}/{number:03d}"


def find_lga_key(value):
    """Match an LGA by key, display name or loose spelling; None if unknown."""
    wanted = normalise_name(value)
    for key, name, _ in KANO_LGAS:
        if wanted in (normalise_name(key), normalise_name(name)):
            return key
    return None


def find_ward_index(lga_key, value):
    """Match a ward of the given LGA by loosely spelled name; None if unknown."""
    wanted = normalise_name(value)
    for index, name in enumerate(LGA_WARDS[lga_key]):
        if normalise_name(name) == wanted:
            return index
    return None
