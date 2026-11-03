# Fresh-PC checklist for Windows 1.0

Release readiness needs the scenarios to pass on at least one fresh Windows 10 and one fresh Windows 11
PC ([TRIAGE.md](TRIAGE.md)). No such PC has been tested yet, and every result so far comes from the build PC.

**A fresh PC** has no Python, VLC or development tools, and has never had Babarify Frame installed. A
friend's or family member's PC is fine, or a new Windows user account if that's all you have. Note in the
results that a new account shares the PC's installed software, so it's weaker evidence.

**Time:** about 20 minutes. **Bring:** one or two video files you're happy to describe in public.

Download from the [0.9.1 release](https://github.com/tanveerbaber-lgtm/Babarify-Frame/releases/tag/v0.9.1):
`BabarifyFrame-0.9.1-setup.exe` and `SHA256SUMS.txt`.

## Record first

- Windows edition and version (`winver`):
- PC model, and whether it's truly fresh or a new account:
- Antivirus, if not only Windows Security:

## Steps

Scenario IDs match [TEST_SCENARIOS.md](TEST_SCENARIOS.md). Tick pass or fail, and open a
[problem report](https://github.com/tanveerbaber-lgtm/Babarify-Frame/issues/new/choose) with the ID for any failure.

| Done | ID | Do this | Pass when |
|---|---|---|---|
| ☐ | INS-1 | In PowerShell, in the download folder: `Get-FileHash .\BabarifyFrame-0.9.1-setup.exe -Algorithm SHA256` | The hash matches `SHA256SUMS.txt` |
| ☐ | INS-2 | Run the installer and choose **Full**. If SmartScreen appears, note what it says, then choose *More info → Run anyway* | No administrator prompt; a Start menu entry appears; the app starts |
| ☐ | — | Note how long the **first** launch takes | Write the seconds down. The build PC took about 13 s, and we don't know yet if that's normal |
| ☐ | — | Open one of your videos; try pause, seek and volume | Picture and sound work |
| ☐ | INS-4 | Reinstall with "Open with" ticked, then right-click a video → Open with | Babarify Frame is offered; your default player hasn't changed |
| ☐ | INS-6 | Uninstall from *Settings → Apps*; answer **No** to deleting data | Program gone; reinstalling shows your settings again |
| ☐ | INS-3 | Uninstall, then install with **Compact** | Installs; *Settings → AI features* says the component isn't installed |
| ☐ | INS-7 | Uninstall; answer **Yes** to deleting data | `%APPDATA%\Babarify` and `%LOCALAPPDATA%\Babarify` are gone; your media is untouched |
| ☐ | ACC-2 | Before the last uninstall, if you can: Narrator (Ctrl+Win+Enter) on Settings and the player controls | Every control is announced with a meaningful name |

**Can't be run yet:** INS-5 (installing a newer beta over an older one). Only 0.9.1 is public, so it waits for
the next beta. The release check covered upgrades on the build PC only.

## Afterwards

Do this once on Windows 10 and once on Windows 11. Send the results, including passes, as a
*Feedback* issue, leaving out anything private. "It worked" is evidence too, and it's what's needed for 1.0.

## Inviting testers

Paste and adjust:

> I've made a free, privacy-focused video player for Windows 10 and 11, Babarify Frame, and it's in public
> beta. There's no account, no ads and no tracking. Would you try it on your PC for about 20 minutes?
>
> Windows may warn that it doesn't recognise the app, because the installer isn't code-signed yet. The steps
> explain how to check the download first.
>
> Download: https://github.com/tanveerbaber-lgtm/Babarify-Frame/releases/tag/v0.9.1
> What to try: https://github.com/tanveerbaber-lgtm/Babarify-Frame/blob/main/docs/beta/FRESH_PC_CHECKLIST.md
> Tell me what you find: https://github.com/tanveerbaber-lgtm/Babarify-Frame/issues/new/choose
>
> Reports are public, so please leave out private file names. It needs a free GitHub account; if you'd rather
> not make one, just tell me directly.
