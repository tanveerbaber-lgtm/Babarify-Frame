# M14 — iOS licensing and dependency review

An engineering review to frame a decision. It is **not legal advice**, and a lawyer should review any
route before the project relies on it.

## The conflict

The GPL doesn't allow further restrictions on recipients, and the FSF's position is that App Store
terms impose them.

- In 2010 the [FSF objected to GNU Go on the App Store](https://lwn.net/Articles/391423), and that
  dispute concerned GPL code the FSF held the copyright to.
- In January 2011 [Apple removed VLC](https://www.fierce-network.com/developer/apple-removes-vlc-media-player-from-app-store)
  after a VLC developer complained.
- In 2013 VLC [returned as a rewrite](https://thenextweb.com/news/vlc-for-ios-will-return-to-the-app-store-on-july-19-full-re-write-open-source-licensed-under-mplv2-and-gplv2?fromcat=all),
  licensed under [GPLv2+ and MPLv2 "for AppStore compatibility"](https://images.videolan.org/press/ios2out.html).
  VideoLAN also moved libVLC to the LGPL. The sources differ on some details of that sequence.

So there's a precedent, and it took relicensing by the people entitled to do so.

Babarify Frame is GPL-3.0-or-later (owner decision, M10).

## What was found in VLCKit

| Check | Result |
|---|---|
| Version resolved | MobileVLCKit 3.7.5 (CocoaPods) |
| `COPYING.txt` in the pod | GNU **LGPL 2.1** |
| Device binary size | 99 MB (before thinning; includes 32-bit slices); simulator 83 MB ([list](evidence/vlckit-binaries.txt)) |
| Text markers in the device binary | `x264` 21, `x265` 3, "GNU General Public" 21, "GPL-2.0-or-later" 6, "GPL-3.0" 6, "LGPL-2.1-or-later" 6 ([scan](evidence/vlckit-markers.txt)) |
| Markers not found | `GPL-2.0-only`, "version 2 only", `libpostproc`, `liba52`, `libdca`, `libfaad` |

**How to read this.** These strings don't prove GPL code is linked: `x264` can appear in decoder code, and
licence text can be embedded in other ways. But they mean the LGPL label can't simply be taken at face
value. **The pod's real contents must be established from VideoLAN's build configuration** before relying
on an LGPL-only route. Even LGPL has conditions on letting users relink, which raise their own
questions on iOS.

AVPlayer has no third-party dependency to review; it's part of iOS.

## Routes

| Route | What it takes | Engine | Main risk |
|---|---|---|---|
| **A. Keep GPL, no App Store** | Nothing to change | VLCKit | Almost nobody can install it. EU marketplaces may be an opening, but whether their [terms](https://developer.apple.com/support/alternative-app-marketplace-in-the-eu) suit the GPL is **unknown**, and they reach EU users only |
| **B. App Store, AVPlayer only** | The app's own code needs a licence route (see below) | AVPlayer | Only MP4-family files, so a much narrower product |
| **C. App Store with VLCKit** | Own-code route, plus confirming VLCKit's contents and obligations; possibly asking VideoLAN | VLCKit | Highest legal uncertainty; the markers above may block it |
| **D. No iOS for now** | Nothing | none | iOS users aren't served. Windows and Android carry on unaffected |

**The app's own code.** A copyright holder can generally offer their code under other terms, by
relicensing, dual licensing or a GPLv3 §7 additional permission. That depends on owning all of it, so a
lawyer should confirm ownership, including code written with AI assistance, and it gets harder once
outside contributions arrive. The repository is public, so **this is simpler to decide before accepting
contributions.**

## Recommendation

Choose between B, C and D with a lawyer's advice before any M15 work. Until then there's nothing to change:
the project stays GPL-3.0-or-later on all platforms. Neither VLCKit nor the prototype is distributed.

The prototype's bundled test clips are synthetic and made for this project. Patent questions on formats
apply here as they do on Windows and Android, and remain open.
