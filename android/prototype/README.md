# Android feasibility prototype (M12)

A measurement tool, **not a product**: one Kotlin activity and one small engine interface, built
once per engine (`media3`, `vlc`). Results and recommendation:
[M12 report](../../docs/milestones/M12/acceptance-report.md).

Needs the Android SDK (API 37) and JDK 17 or later. Put `sdk.dir` in `local.properties`.

```bash
./gradlew assembleRelease
```

With a phone connected and unlocked, from the repository root:

```bash
.venv/Scripts/python tools/android_probe.py
```

```bash
.venv/Scripts/python tools/android_probe.py --cleanup
```

APKs are signed with the debug key and must not be distributed.
