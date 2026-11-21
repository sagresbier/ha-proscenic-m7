"""Konstanten der Proscenic-M7-Integration."""
from __future__ import annotations

DOMAIN = "proscenic_m7"
CONF_SERIAL = "serial"

# mode-Werte aus dem App-Code (Proscenic Home 1.5.5), bisher nur "dormant" real beobachtet
CLEANING_MODES = {
    "sweep", "mop", "areaing", "areamoping", "pointing", "curpointing",
    "depthtotalclean", "depthtotalmop", "totaling", "selectroom", "remotectl",
}
RETURNING_MODES = {"tocharge", "backcharge"}
PAUSED_MODES = {"pause", "findchargerpause"}
CHARGING_MODES = {"chargring", "charge"}  # "chargring" ist so im App-Code geschrieben

STATUS_OPTIONS = [
    "cleaning", "returning", "paused", "charging", "charged",
    "idle", "dormant", "error", "unknown",
]

# Fehlercodes aus dem App-Code; alles andere -> "other"
ERROR_KEYS = {
    -2402: "side_brush",
    -2401: "main_brush",
    -2201: "main_wheel",
    5059: "charging_stand",
}
ERROR_OPTIONS = ["none", "side_brush", "main_brush", "main_wheel", "charging_stand", "other"]


def normalize_status(mode: str | None) -> str:
    """Ordnet den rohen mode-Wert einem festen Zustand zu."""
    if mode is None:
        return "unknown"
    if mode == "fault":
        return "error"
    if mode in CLEANING_MODES:
        return "cleaning"
    if mode in RETURNING_MODES:
        return "returning"
    if mode in PAUSED_MODES:
        return "paused"
    if mode in CHARGING_MODES:
        return "charging"
    if mode == "fullcharge":
        return "charged"
    if mode == "idle":
        return "idle"
    if mode == "dormant":
        return "dormant"
    return "unknown"


def error_codes(status: dict) -> list[int]:
    """Liste der aktiven Fehlercodes (errorState)."""
    codes = status.get("errorState") or []
    return [c for c in codes if isinstance(c, int)]


def error_key(status: dict) -> str:
    """Wichtigster Fehler als Schluessel fuer die Uebersetzung."""
    codes = error_codes(status)
    if not codes:
        return "none"
    return ERROR_KEYS.get(codes[0], "other")
