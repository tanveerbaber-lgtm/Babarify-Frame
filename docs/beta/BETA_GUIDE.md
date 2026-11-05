# Babarify Media Player beta — guide for testers

Thank you for helping. The beta is a free, privacy-focused media player for Windows 10 (1809 or
later) and Windows 11, 64-bit.

1. **Install:** download `BabarifyMediaPlayer-<version>-setup.exe` and `SHA256SUMS.txt` from the
   release page, check the hash (`Get-FileHash … -Algorithm SHA256`), then run the installer.
   It is not code-signed yet; see Known issues.
2. **Test:** use it with your own files, and if you have time, work through
   [TEST_SCENARIOS.md](TEST_SCENARIOS.md).
3. **Report:** open an issue with the *Problem report* or *Feedback* form. In the app,
   *Help → Report a problem* prepares the technical details for you to paste. Security or
   privacy problems: report them privately (link on the new-issue page).
4. **Check** [KNOWN_ISSUES.md](KNOWN_ISSUES.md) first.

## What we collect

Only what you write into an issue. The app has no telemetry, no crash upload and no account.
Its logs stay on your PC (`%LOCALAPPDATA%\Babarify\Frame\logs`); share lines from them only if
you want to. Issues are public: leave out names of private files and addresses of private
streams. See [PRIVACY.md](../PRIVACY.md).

## Leaving the beta

Uninstall from *Settings → Apps* and choose whether to delete your Babarify data. Issues you
opened can be closed or edited by you at any time.
