# T00 spike — make the device display our image

Throwaway. Proves a server we control can put a chosen image on the TRMNL panel,
before anything real is built on that assumption. Deleted once T00's findings are
in `../plans/trmnl-dashboard/FINDINGS.md`.

## Run

On the home box (or the dev Mac) **on the same wifi as the device**:

```
python3 spike/server.py
```

Pure standard library — no Docker, no Pillow needed to run it. It prints a LAN
base URL, e.g. `http://192.168.0.88:2300`, and then logs every request the
device makes.

## Point the device at it

1. Put the TRMNL into wifi setup (first boot, or hold the button to re-run it).
2. From a phone, join the device's own setup access point.
3. Choose the home wifi, and set the **server base URL** to the printed LAN URL.
4. Within a refresh cycle the panel should show our image: a framed screen
   reading **TRMNL SPIKE / IT DISPLAYS OUR IMAGE**.

Fully resettable: re-running the captive portal (or `reset_firmware`) changes the
URL back, so this cannot lock the device to us.

## What to read afterward

The server prints, for every request, the exact path and every header. That log
is the evidence T00 wants: the paths the firmware calls, the header names and
casing it sends (its MAC in `ID`, maybe `ACCESS_TOKEN`), and the firmware version.

## Regenerate the image (optional)

`spike.bmp` is committed, so the server needs nothing to run. To rebuild it you
need Pillow:

```
python3 spike/make_image.py
```
