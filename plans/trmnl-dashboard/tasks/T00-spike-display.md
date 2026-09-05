# T00 — Spike: make the device display a static image from our server

**Phase:** 0 · **Depends on:** — · **Weight:** heavy (physical unknowns, hand-verified)

## Goal

Prove, on the real device, that a server we control can make the TRMNL show an image we choose.
This retires the biggest risk in the whole plan before anything is built on it: that the BYOS
HTTP contract works as researched, that an 800×480 1-bit BMP is accepted and drawn correctly,
and that the wifi captive portal will point the device at a LAN server URL. It is also the
owner's stated first goal — "make it display anything". The code is throwaway and is deleted
once its findings are in FINDINGS.md.

## Design sections this implements

DESIGN.md §2.5 (the `refresh_rate` response), §5.1 (device is hand-verified), §5.2 (static
test image seatbelt). This task exists to confirm the assumptions those sections rest on.

## Files

A throwaway script or tiny app under `spike/` (not part of the real package layout, which T01
creates). One hardcoded 800×480 1-bit BMP asset. Nothing here is kept.

## Interface

The minimum BYOS surface the firmware needs:

```
GET /api/setup      -> 200 {"api_key":"<any>","friendly_id":"<any>","image_url":"<url>","status":200}
GET /api/display    -> 200 {"filename":"spike","image_url":"http://<lan-ip>:<port>/spike.bmp","refresh_rate":900}
GET /spike.bmp      -> the 800x480 1-bit BMP3 bytes
POST /api/log       -> 204
```

Read request headers case-insensitively; the device sends `ID` (its MAC) and, after setup,
`ACCESS_TOKEN`. Bind to the LAN interface so the device can reach it. `refresh_rate` of 900 is
fine for the spike — fast refresh is a later concern.

## Tests

Automated tests are not the evidence here; the device is (see "Needs a person"). A couple of
sanity checks are still worth writing while building:

- [ ] The BMP asset is genuinely 800×480, 1-bit — verify with `PIL.Image.open(...).mode == "1"`
      and size, or `file`/`identify`, before ever handing it to the device.
- [ ] `/api/display` returns valid JSON with an absolute `image_url` the device can resolve.

## Done when

- [ ] The physical TRMNL, pointed at this server through its captive portal, shows our image.
- [ ] FINDINGS.md records: the exact request the device made (path + headers actually seen), the
      image format that worked, and anything that differed from the research in DESIGN/FINDINGS.
- [ ] The `spike/` code is removed in the same task once the findings are written.

## Needs a person

This is the whole point of the task and it needs the owner and the device. Raise it and wait.

```
1. Start the spike server on the home box (or dev Mac on the same wifi):
     <the run command>   # prints the LAN URL, e.g. http://192.168.0.20:2300
2. On the TRMNL: run its wifi setup (hold the button / first boot), join the device's
   setup access point from a phone, choose the home wifi, and set the server base URL
   to the printed LAN URL. Seatbelt: this is fully resettable — re-running setup undoes it.
```

Expect: within a refresh cycle the screen shows our static image.
Tell me: did it display; if not, what did the screen say; and (from the server log) the exact
path and headers the device sent, plus the firmware version in the headers.
