# Proscenic M7 Pro for Home Assistant

Unofficial Home Assistant integration for the **Proscenic M7 Pro** robot vacuum. It talks to the legacy
**Proscenic Home** cloud (`mobile.proscenic.com.de`) and gets status updates by push.
It is not affiliated with or endorsed by Proscenic. Use at your own risk.

> **Deutsch:** Inoffizielle Integration für den Proscenic M7 Pro (alte Proscenic-Home-Cloud). Zeigt Zustand, Akku,
> Fläche, Zeit und Fehler an und steuert Start, Pause, Station, Saugstärke, Tiefenreinigung und Behälter leeren.
> Einrichtung per Benutzername und Seriennummer, ein Token wird nicht benötigt. Die Hinweise unten gelten auch für die deutsche Version.

## Features

- `vacuum` entity: start (resumes when paused), pause, return to dock, suction level (quiet / standard / powerful),
  `vacuum.send_command` with `clean`, `deep_clean`, `empty_dust`, `pause`, `continue`, `charge`
- Buttons: deep clean, empty dust bin
- Sensors: status, battery, cleaned area, cleaning time, total area, total time, error
- Binary sensors: problem (active error code), robot online
- Push connection with automatic reconnect; a fresh token is requested on every connect and never stored

## Requirements

- A robot that is bound to the **legacy Proscenic Home app** (cloud `mobile.proscenic.com.de`).
  Newer Proscenic models and the newer Tuya-based Proscenic app are **not** supported.
- The e-mail address (user name) and the serial number of the robot, as shown in the Proscenic Home app.

## Installation

**HACS (custom repository):** HACS → three-dot menu → Custom repositories →
`https://github.com/sagresbier/ha-proscenic-m7`, category *Integration* → install → restart Home Assistant.

**Manual:** copy `custom_components/proscenic_m7` to `<config>/custom_components/` and restart.

Then add the integration under *Settings → Devices & services → Add integration → Proscenic M7 Pro*.

## Notes and limitations

- Tested with one robot (M7 Pro). Other models on the same cloud may report other `mode` values and error codes.
- Only the mode `dormant` was observed on a real robot so far. The other modes (`sweep`, `pause`, `tocharge`, ...) and
  the suction mapping (`quiet` / `auto` / `strong`) are derived from the app and from existing REST scripts.
  Unknown values show up as "Unknown"; the raw value is available in the attribute `mode`.
- Only four error codes are translated (side brush, main brush, main wheel, charging dock). All other codes are
  shown as "Other error" with the codes in the attribute `error_codes`.
- Status is polled every 20 seconds (heartbeat every 6 seconds) and once more 3 seconds after each command.
- Entity IDs depend on your device name, area and the entity naming settings of your Home Assistant version.
- This is based on the observed behavior of the app. If the cloud changes, the integration may stop working.

## Dashboard example

A ready-to-paste card that only uses built-in Home Assistant cards is in
[`examples/dashboard.yaml`](examples/dashboard.yaml). Replace `DEVICE` with the name part of your
entity IDs and adjust the sensor names if your Home Assistant uses another language.

## Tests

The tests use a simulated cloud and run in the Home Assistant test framework:

```bash
pip install -r requirements_test.txt
pytest tests
```

## Credits

The control requests (paths and bodies) follow the REST commands of
[andker87/Proscenic-M7-PRO](https://github.com/andker87/Proscenic-M7-PRO). Thanks for that groundwork.

## License

MIT, see [LICENSE](LICENSE).
