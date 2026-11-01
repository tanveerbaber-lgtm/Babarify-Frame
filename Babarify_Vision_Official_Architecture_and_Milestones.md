# Babarify Frame
## Official Product Architecture and Complete Milestone Plan

**Document status:** Proposed official project baseline  
**Product:** Babarify Frame  
**Parent brand:** Babarify  
**Tagline:** Every Frame, Better.  
**Business model:** Free for everyone  
**Initial platform:** Windows 10 and Windows 11, 64-bit  
**Future platforms:** Android and iOS, with the cross-platform strategy decided after technical validation  
**Playback engine:** Not selected. Benchmark libVLC and mpv before making the production choice.  
**Document purpose:** Architecture reference, product scope, implementation roadmap, quality gates, and milestone tracking.

---

## 1. Executive Summary

Babarify Frame is planned as a modern, privacy-focused media player designed to compete with established players such as VLC and PotPlayer through a polished interface, dependable playback, useful advanced controls, accessible media management, and carefully chosen intelligent features.

The project must not attempt to recreate every mature media-engine feature immediately. It should first establish a maintainable architecture, compare playback technologies using reproducible tests, review licensing and distribution obligations, and then build a reliable Windows player in validated stages.

The product will be free to use. The baseline includes no advertising, no mandatory account, no automatic upload of personal media, and no telemetry enabled by default. Optional online services, if added in later milestones, must be clearly disclosed and controlled by the user.

### Product principles

1. **Playback reliability first.** A beautiful interface is not a substitute for dependable playback.
2. **Evidence before architecture commitments.** Select the engine using actual measurements, compatibility tests, licensing review, and maintainability.
3. **Simple by default, powerful when needed.** Keep common playback controls obvious and advanced settings discoverable.
4. **Local-first privacy.** Local playback and library functions should not require an account or a network connection.
5. **Honest capabilities.** Do not claim universal HDR, 8K, hardware decoding, AI enhancement, or codec support without verified device-specific evidence.
6. **Modular implementation.** Keep the interface independent of the selected playback engine.
7. **Milestone gates.** Every milestone must have tests, evidence, documented limitations, and an explicit acceptance decision.
8. **Licensing as a release requirement.** Free distribution does not remove third-party license, patent, attribution, or redistribution obligations.

---

## 2. Product Identity and Scope

### 2.1 Identity

- **Official product name:** Babarify Frame
- **Brand:** Babarify
- **Tagline:** Every Frame, Better.
- **Visual direction:** Premium dark interface, restrained blue/cyan highlights, and green accents consistent with the Babarify brand.
- **App icon:** A glowing blue "B" (for Babarify) with a green-cyan play symbol in its upper bowl, an orbiting green ring, and a small sparkle, on a dark rounded tile with a blue-to-green border. The source artwork is `branding/source/babarify-frame-source.webp`; `branding/generate_icon.py` crops it to the tile and builds the PNG sizes (16–1024 px) and the multi-size Windows `.ico` in `branding/icon/`. The source is raster at 1254 px, so a vector master should be commissioned before large-format or store use.
- **Audience:** People who want a reliable, attractive, capable desktop player for personal video and audio collections.

The name and tagline are proposed product decisions, not trademark clearance. Check relevant trademark databases, domains, software listings, and naming conflicts before public release.

### 2.2 Platforms

**Phase 1:** Windows 10 and Windows 11, 64-bit.

**Future:** Android and iOS. These are roadmap targets, not M1 deliverables. Before mobile implementation, decide whether to share a cross-platform UI, use native clients, or use a hybrid architecture. Do not assume that the Windows UI toolkit or native playback binaries can simply be reused on mobile.

Linux and macOS are not committed initial targets. They may be considered after the Windows product is stable and the engine and packaging strategy are understood.

### 2.3 Business and privacy model

- Free for everyone.
- No advertising.
- No mandatory account for local playback.
- No automatic upload of media, subtitles, or library contents.
- No telemetry enabled by default.
- Optional cloud or AI features must require explicit user choice, disclose what data leaves the device, and provide a way to use the core player without them.
- No collection of media filenames or viewing history for marketing.
- Secure update checks and crash reporting must be transparent and privacy-conscious.

### 2.4 Product boundaries

Babarify Frame is a media player and media-library application. It is not initially a video editor, transcoding suite, streaming subscription service, or media-hosting platform. Conversion, streaming, AI features, and remote control are later optional modules subject to feasibility, security, and licensing review.

---

## 3. Competitive Positioning

Established players already provide broad format support, streaming, advanced controls, and rendering options. Babarify Frame should not claim that it is universally better than VLC before it is tested. It should aim to win through a better overall experience.

### Areas of differentiation

1. Modern, consistent interface with a clean basic mode and an advanced mode.
2. Continue Watching and resume support that works reliably.
3. A useful local library with search, playlists, collections, and thumbnails.
4. A practical subtitle studio with timing, appearance, track selection, and accessibility options.
5. Clear performance diagnostics showing codec, resolution, frame rate, decoder status, and useful errors.
6. User-configurable picture and audio profiles.
7. Privacy-first defaults and transparent optional online features.
8. Stable, signed, clearly documented Windows installation and removal.

### Success measures

- High playback success rate on the declared test corpus.
- No recurring crashes or resource leaks in long-running tests.
- Smooth UI response during playback and library scanning.
- Accurate playback state and resume position.
- Clear handling of unsupported files and unavailable capabilities.
- Reproducible builds and a documented dependency/license inventory.
- Positive usability feedback from real users before public release.

Do not invent numerical success targets. Set target thresholds before a benchmark run, document why they are appropriate, and revise them only with an explanation.

---

## 4. Official Technical Architecture

### 4.1 Layered design

```text
Babarify Frame
|
+-- Presentation Layer
|   +-- Home
|   +-- Library
|   +-- Playback Window
|   +-- Subtitle Studio
|   +-- Picture and Audio Settings
|   +-- Preferences and Diagnostics
|
+-- Application Layer
|   +-- Playback Controller
|   +-- Playlist Service
|   +-- Resume and History Service
|   +-- Bookmark Service
|   +-- Media Library Service
|   +-- Settings Service
|   +-- Capability and Error Mapping
|
+-- Playback Abstraction
|   +-- Common Playback Contract
|   +-- Engine Factory
|   +-- libVLC Adapter (candidate)
|   +-- mpv Adapter (candidate)
|   +-- Mock Adapter (tests)
|
+-- Platform and Infrastructure Layer
|   +-- Windows File and Window Integration
|   +-- SQLite Persistence
|   +-- Thumbnail and Metadata Workers
|   +-- Logging and Diagnostics
|   +-- Packaging and Update Support
|
+-- External Dependencies
    +-- Selected Playback Engine
    +-- Engine Plugins and Codecs
    +-- UI Framework
    +-- Approved Python Packages
```

The presentation layer must not call libVLC or mpv APIs directly. All engine operations must go through the playback abstraction. This allows the engine to be replaced or tested without rewriting the application UI.

### 4.2 Proposed initial technology stack

| Area | Initial proposal | Validation required |
|---|---|---|
| Desktop language | Python | Confirm compatibility with selected bindings and packaging |
| UI | PySide6 / Qt 6 | Validate licensing route, deployment, accessibility, and visual performance |
| Candidate engine A | libVLC | Validate playback, plugins, packaging, licensing, and performance |
| Candidate engine B | mpv | Validate library integration, output, packaging, licensing, and performance |
| Persistence | SQLite | Define schema, migrations, and corruption recovery |
| Configuration | Typed configuration models plus JSON or SQLite as appropriate | Avoid duplicate sources of truth |
| Testing | pytest and suitable static/type checks | Pin compatible versions |
| Packaging | Windows packaging/installer tool selected later | Validate clean install, update, uninstall, and signing |
| CI | Git-based CI when repository hosting is chosen | Run deterministic tests and linting |
| Mobile | Not selected | Decide after Windows architecture and engine feasibility are validated |

Python/PySide6 is a proposed fast-development path for the Windows prototype, not a permanent cross-platform decision. Avoid committing the project to a mobile strategy before the required playback engine and interface constraints are understood.

### 4.3 Playback abstraction

The first shared contract should support operations equivalent to:

- `open_media(uri)`
- `play()`
- `pause()`
- `stop()`
- `seek(position_ms)`
- `set_volume(level)`
- `set_muted(enabled)`
- `set_playback_rate(rate)`
- `get_playback_state()`
- `get_media_info()`
- `get_capabilities()`
- `close()`

It should define typed models for:

- Media metadata.
- Playback state.
- Engine capabilities.
- Playback errors.
- Track information.
- Engine lifecycle and playback events.

Use a clear lifecycle: uninitialized, ready, loading, playing, paused, buffering where relevant, ended, error, and closed. Avoid invalid transitions and ensure resources are released after errors or application shutdown.

Capability reporting is important. If an engine or device does not support a feature, the UI must disable it or explain the limitation instead of simulating support.

### 4.4 Concurrency and responsiveness

- Keep the UI event loop responsive.
- Run media scanning, thumbnail extraction, and expensive metadata work on worker threads or processes where appropriate.
- Respect the threading and callback requirements of the chosen playback engine.
- Send normalized events to the UI through safe, documented mechanisms.
- Avoid sharing engine objects across threads unless the engine explicitly supports it.
- Provide cancellation for background scans.
- Cleanly stop workers and playback before application shutdown.

### 4.5 Persistence

Use SQLite for structured local information such as:

- Playback history.
- Resume positions.
- Bookmarks.
- Playlists and playlist items.
- Library folder roots and media metadata.
- User preferences if the chosen design stores them in SQLite.

Keep transient playback state out of the database unless it must survive restarts. Use schema migrations, transactions, and tests for recovery. Avoid scanning the user's entire disk by default. Library access must be user-directed and understandable.

### 4.6 Security

- Treat filenames, playlists, subtitles, network streams, and media metadata as untrusted input.
- Do not expose arbitrary shell execution through media actions.
- Validate paths and URIs according to the selected engine's requirements.
- Do not auto-open remote streams or download subtitle files without a clear user action or configured preference.
- Keep optional network features off until their security and privacy behavior is designed.
- Use least privilege and avoid unnecessary administrator permissions.
- Test malformed inputs and failure cleanup with safe test fixtures.
- Sign production binaries and installers where practical.
- Provide a transparent update channel and verify update integrity.

---

## 5. Proposed Repository Structure

```text
Babarify.Frame/
├── README.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml
├── .gitignore
├── .editorconfig
│
├── apps/
│   ├── desktop-windows/
│   │   ├── src/babarify_frame/
│   │   │   ├── main.py
│   │   │   ├── bootstrap.py
│   │   │   ├── ui/
│   │   │   ├── viewmodels/
│   │   │   └── resources/
│   │   └── tests/
│   ├── android/       # Future milestone only
│   └── ios/           # Future milestone only
│
├── packages/
│   ├── frame-core/
│   │   ├── models/
│   │   ├── interfaces/
│   │   ├── events/
│   │   └── errors/
│   ├── playback/
│   │   ├── contracts.py
│   │   ├── controller.py
│   │   ├── capabilities.py
│   │   └── adapters/
│   │       ├── libvlc/
│   │       └── mpv/
│   ├── media-library/
│   ├── persistence/
│   ├── configuration/
│   └── diagnostics/
│
├── tools/
│   ├── engine-benchmark/
│   ├── license-audit/
│   └── test-media-manifest/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── playback/
│   ├── performance/
│   └── fixtures/
│
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── licensing/
│   ├── testing/
│   ├── benchmarks/
│   └── milestones/
│       └── M1/
│
└── packaging/
    └── windows/
```

Create only directories and files needed for a real M1 deliverable. Do not fill the repository with empty placeholders. Adapt this structure if an existing repository already contains user work or a well-justified layout.

---

## 6. Playback Engine Selection Policy

### Candidate A: libVLC

Potential strengths:
- Mature playback engine and broad media support.
- Embeddable library interface.
- Existing streaming and media functionality.

Questions to test:
- Exact plugin and codec configuration.
- Distribution and licensing obligations for the selected build.
- Integration complexity with the chosen UI framework.
- Hardware-decoding behavior on target Windows hardware.
- Performance, stability, and feature access through the binding.

### Candidate B: mpv

Potential strengths:
- High-quality rendering and extensive playback configuration.
- Library interface and useful playback control surface.
- Strong potential for advanced rendering workflows.

Questions to test:
- Integration and event-loop behavior.
- Packaging of the chosen build and its dependencies.
- Exact license and linked dependency obligations.
- Subtitle and track controls required by the product.
- Hardware decoding, fallback, and long-session stability.

### Benchmark protocol

Use the same machine, OS, GPU driver, display setup, legal test media, and test scenarios. Record engine versions and configuration. Run repeated trials and report medians and ranges. Separate cold starts from warm starts.

Measure:
- Successful initialization and media opening.
- Startup latency.
- Seek response.
- Playback stability.
- CPU and memory use.
- Hardware decoding and fallback.
- Audio and subtitle track access.
- State events and error reporting.
- Resource cleanup.
- Packaging complexity.
- Integration effort.
- Suitability for a later mobile roadmap.

Do not select a winner using a single test or a small startup-time difference. Reliability, feature coverage, licensing, and maintainability are essential. If evidence is incomplete, leave the decision open and define the next test.

---

## 7. Licensing and Distribution Policy

A free application still has licensing obligations. Do not assume that an engine's headline license applies to all its plugins, codecs, or dependencies.

For every direct and transitive dependency, record:
- Name and version.
- License identifier and license text.
- Source or official project location.
- Whether it is a development-only dependency or distributed with the product.
- Whether source disclosure, notices, relinking, or other obligations may apply.
- Known restrictions and unresolved questions.
- Person or reviewer responsible for resolution.

Review at minimum:
- libVLC and enabled plugins.
- mpv and the actual linked dependencies/build configuration.
- PySide6/Qt modules and the chosen licensing route.
- FFmpeg, if used, including enabled components and build flags.
- Python packages and bundled binaries.
- Codec patent and distribution considerations in target territories.
- Product name, logo, and trademark conflicts.

Create a preliminary report distinguishing verified facts, assumptions, unresolved questions, and items requiring legal review. Do not claim formal legal clearance based solely on an automated scan. Do not publish a production installer until distribution requirements are understood.

Official reference points:
- libVLC documentation: https://videolan.videolan.me/vlc/master/libvlc.html
- mpv project: https://mpv.io/
- Qt licensing: https://doc.qt.io/qt-6/licensing.html
- FFmpeg legal guidance: https://ffmpeg.org/legal.html

---

## 8. Full Milestone Roadmap

The milestones below define the intended scope. A milestone is not complete because its code exists. It is complete only when its acceptance criteria are evidenced and reviewed. Update status only after reviewing actual implementation reports and test results.

### M1 — Feasibility and Architecture

**Goal:** Establish a reproducible foundation and compare libVLC and mpv.

Deliverables:
- Environment and repository inspection.
- Minimal branded desktop shell.
- Common playback contract, typed state models, and mock adapter.
- Separate engine prototypes and benchmark harness, where feasible.
- Preliminary dependency and license inventory.
- Unit tests, static checks, setup documentation, and acceptance report.
- Architecture decision record that selects an engine only if evidence is sufficient.

Acceptance:
- Reproducible setup instructions.
- Shell launches and closes cleanly.
- Mock adapter and contract tests pass.
- Actual benchmark data or documented blockers exist.
- Licensing risks and unknowns are recorded.
- No unrelated user changes were discarded.
- M1 report marks each criterion PASS, CONDITIONAL, FAIL, or BLOCKED.

Do not build the complete player in this milestone.

### M2 — Real Playback Prototype

**Goal:** Play real local media using the selected engine.

Deliverables:
- Selected engine adapter integrated with the playback controller.
- Open file, play, pause, stop, seek, volume, mute, and fullscreen.
- Clear loading, playing, paused, ended, and error states.
- Media open failures handled without crashing.
- Resource cleanup and repeated open/close tests.
- Initial test corpus covering common containers and codecs.

Acceptance:
- Real playback is demonstrated on the target Windows environment.
- Basic controls work on verified test files.
- Invalid or unsupported files fail gracefully.
- No known critical resource leak or recurring crash remains.
- Engine-specific code remains behind the adapter.
- Test results and limitations are documented.

### M3 — Premium UI Foundation

**Goal:** Create a consistent, polished interface without sacrificing usability.

Deliverables:
- Main application shell and navigation.
- Video area and playback control layout.
- Dark theme with Babarify blue/cyan and green accents.
- Responsive resizing and fullscreen transitions.
- Keyboard shortcuts and accessible control labels.
- Empty, loading, error, and no-media states.
- Basic preferences and persistence for UI settings.

Acceptance:
- UI remains responsive during playback.
- Common actions are easy to find.
- Keyboard focus and shortcuts behave consistently.
- Window resizing and fullscreen transitions work reliably.
- Branding and spacing remain consistent across the application.

### M4 — Playback Reliability and Performance

**Goal:** Improve reliability across common media and target hardware.

Deliverables:
- Expanded test corpus with manifest and checksums.
- Hardware-decoding capability detection and safe fallback.
- Diagnostics for codec, resolution, frame rate, decoder status, and playback errors.
- Long-session, repeated-open, seeking, and shutdown tests.
- CPU and memory measurements under defined conditions.
- Regression tests for previously discovered failures.

Acceptance:
- Declared test cases have recorded results.
- Hardware decoding is reported accurately and never falsely promised.
- Unsupported capabilities are handled clearly.
- No unresolved release-blocking crash or data-corruption defect remains.
- Performance claims are based on reproducible measurements.

### M5 — Audio and Subtitle Studio

**Goal:** Deliver reliable track selection and useful synchronization controls.

Deliverables:
- Audio track selection.
- Subtitle track selection and external subtitle loading.
- Subtitle delay and audio delay.
- Subtitle font, size, color, background, and position where supported.
- Clear behavior for missing fonts, unsupported subtitle formats, and unavailable tracks.
- Optional dual subtitles only if the selected engine and UI can support them reliably.

Acceptance:
- Track changes work on verified sample files.
- Synchronization controls have clear, predictable units and reset behavior.
- Subtitle settings persist according to user preference.
- Unsupported formats and engine limitations are disclosed.
- No subtitle or media content is uploaded without explicit user action.

### M6 — Media Library and Personal History

**Goal:** Make the player useful for a personal collection without requiring a library.

Deliverables:
- User-selected library folders.
- Media scanning on background workers.
- Search, sort, recently played, and playlists.
- Resume positions and continue watching.
- Thumbnails and media metadata.
- SQLite schema migrations and recovery tests.
- Controls to remove library entries and clear history.

Acceptance:
- Library scanning does not freeze playback or the UI.
- Duplicate files and unavailable files are handled predictably.
- Resume positions are accurate within a documented tolerance.
- Database migrations and recovery tests pass.
- Users can choose which folders are scanned.
- Local library use works offline.

### M7 — Picture and Audio Enhancement

**Goal:** Add useful, transparent picture and sound controls.

Deliverables:
- Aspect ratio and scaling controls.
- Rotation and crop where supported.
- Brightness, contrast, saturation, and other engine-supported picture controls.
- Audio equalizer and presets where supported.
- Volume boost only with appropriate clipping safeguards.
- A/B repeat, frame stepping, and snapshot features where feasible.
- Reset-to-default controls and saved user profiles.

Acceptance:
- Controls map to real engine functionality.
- Unsupported controls are disabled or explained.
- Presets can be saved, applied, and reset.
- Picture/audio adjustments do not corrupt playback state.
- Performance impact and known limitations are documented.

### M8 — Advanced Media and Network Features

**Goal:** Add advanced playback workflows after core reliability is proven.

Potential deliverables:
- Chapter navigation and timeline bookmarks.
- Seek-bar thumbnail previews.
- Detailed media information.
- 360-degree and stereoscopic playback if technically justified.
- Network streams and supported network media sources.
- Optional media conversion or capture only after licensing and security review.

Acceptance:
- Each feature has independent tests and documented capability requirements.
- Network inputs are treated as untrusted.
- No arbitrary command execution is exposed through media URLs or playlists.
- Unsupported network protocols and media are handled safely.
- Optional modules do not destabilize local playback.

Do not treat every potential feature as mandatory. Select the features that offer real user value and can be maintained safely.

### M9 — Intelligent and Optional AI Features

**Goal:** Add useful intelligent tools while preserving privacy and user control.

Potential deliverables:
- Optional subtitle discovery from approved sources.
- AI-assisted subtitle translation.
- Speech-to-text subtitle generation using a validated local or explicitly enabled cloud provider.
- Local media search using indexed metadata and, optionally, user-approved speech/text indexes.
- Optional scene or chapter summaries.
- User-controlled processing and data deletion controls.

Acceptance:
- AI features are off until explicitly enabled.
- The UI explains whether processing is local or remote.
- Remote processing discloses what information is sent and to whom.
- No media or subtitle is uploaded silently.
- Output is labeled as machine-generated where appropriate.
- Users can disable features and remove associated data.
- Costs, dependencies, licenses, and performance impacts are documented before enabling any service.

### M10 — Windows Packaging, Security, and Release

**Goal:** Produce a reliable, installable Windows release.

Deliverables:
- Production installer and versioning strategy.
- File associations only with user consent or clear Windows conventions.
- Clean install, upgrade, repair, and uninstall behavior.
- Signed binaries/installer where feasible.
- Dependency and third-party notice bundle.
- License compliance review.
- Update integrity and rollback strategy.
- Crash diagnostics and privacy documentation.
- Release notes and user documentation.

Acceptance:
- Install and uninstall succeed on a clean test machine.
- No development-only dependency is accidentally required.
- Packaged playback works without a development environment.
- All distributed binaries and licenses have been reviewed.
- Update and rollback behavior is tested.
- No release-blocking security or stability issue remains.
- Release artifacts and checksums are recorded.

### M11 — Public Beta and User Feedback

**Goal:** Validate the product with a controlled group before general release.

Deliverables:
- Beta build and known-issues page.
- Structured feedback channel.
- Test scenarios for installation, playback, subtitles, library, and settings.
- Triage process and regression tests.
- Accessibility and usability review.

Acceptance:
- Feedback is categorized by severity and reproducibility.
- Critical issues are fixed or block release.
- User data is not collected beyond the documented and consented process.
- Release readiness is decided from evidence, not download counts alone.

### M12 — Android Feasibility and Shared Architecture

**Goal:** Define the mobile architecture without compromising the desktop product.

Deliverables:
- Mobile requirements and UX scope.
- Evaluation of native or cross-platform UI options.
- Android playback engine feasibility prototype.
- Shared data models and portable application contracts where useful.
- Platform-specific capability matrix.
- Mobile licensing and packaging review.

Acceptance:
- Android strategy is based on a real prototype and dependency review.
- Shared contracts are genuinely portable rather than forcing desktop assumptions onto mobile.
- Mobile permissions and media access follow platform rules.
- No Android release is claimed until it is tested on supported devices.

### M13 — Android Implementation

**Goal:** Build and validate an Android player after M12 approval.

Potential scope:
- Local file playback.
- Play/pause/seek/volume and supported audio/subtitle tracks.
- Android media picker and scoped storage compliance.
- Playback history and preferences.
- Screen rotation, background behavior, and battery-aware playback as appropriate.

Acceptance:
- Tested on a defined device/OS matrix.
- Media access is permission-conscious.
- Playback and lifecycle behavior survive supported pause/resume scenarios.
- No unexplained background media access or uploads occur.
- Release packaging and third-party licenses are reviewed.

### M14 — iOS Feasibility and Shared Architecture

**Goal:** Evaluate iOS-specific playback, media access, UI, and distribution constraints.

Deliverables:
- iOS technology and engine feasibility prototype.
- App Store distribution and signing requirements.
- Media picker, sandbox, and background playback review.
- Shared-contract and platform-capability review.
- Licensing and dependency review.

Acceptance:
- Feasibility is demonstrated on supported Apple hardware or simulator where appropriate.
- Platform restrictions and unsupported features are documented.
- No desktop-only assumption is forced into the iOS design.
- A realistic implementation scope is approved before development.

### M15 — iOS Implementation

**Goal:** Build and validate the iOS player after M14 approval.

Potential scope:
- Local media access through supported system interfaces.
- Playback controls and supported subtitle/audio selection.
- Preferences and playback history where permitted.
- Platform-native accessibility and lifecycle behavior.

Acceptance:
- Tested on the declared iOS/device matrix.
- Signing, privacy declarations, and distribution obligations are satisfied.
- Background and interruption behavior is tested.
- All bundled dependencies are reviewed.
- The iOS release is not declared complete before actual device validation.

### M16 — Ongoing Maintenance and Expansion

**Goal:** Maintain a safe, compatible, useful product after launch.

Ongoing work:
- Security and dependency updates.
- Regression testing against OS and GPU driver changes.
- User-requested improvements.
- Accessibility and localization.
- Optional Linux/macOS exploration if justified.
- Performance improvements backed by profiling.
- Documentation, release notes, and support workflow.

Acceptance:
- Each release has a tested build, dependency/license review, and changelog.
- Regressions are tracked and fixed through normal development gates.
- Optional features do not weaken privacy or core playback reliability.

---

## 9. Quality Gates for Every Milestone

Every milestone must include:

1. Scope and acceptance criteria agreed before implementation.
2. Repository inspection and preservation of existing work.
3. Small, reviewable changes.
4. Automated tests appropriate to the milestone.
5. Static checks and dependency checks where applicable.
6. Actual test output and documented skipped/blocked tests.
7. Updated architecture and user documentation.
8. Known issues and unresolved decisions.
9. License/security/privacy impact review when dependencies or data flows change.
10. A completion report with evidence.
11. An explicit decision: PASS, CONDITIONAL, FAIL, or BLOCKED.
12. Approval before starting the next milestone.

Do not update the official progress tracker merely because a prompt was run. Update it only after reviewing the implementation report and evidence.

---

## 10. Test Strategy

### Unit tests
Test playback state transitions, command validation, error mapping, capability reporting, configuration, and mock-adapter behavior.

### Integration tests
Test engine initialization, opening and closing media, event delivery, repeated open/close cycles, and cleanup after errors.

### Playback tests
Use a legally obtained test corpus with a manifest describing format, expected properties, provenance, and checksum. Cover common containers, video/audio codecs, external subtitles, multiple tracks, and larger files as practical.

### Performance tests
Measure startup, seek response, CPU, memory, dropped frames where measurable, and long-session stability. Keep test environment and engine settings recorded. Use repeated runs and report medians and ranges.

### UI tests
Test launch, resize, fullscreen, keyboard controls, error states, focus behavior, and responsiveness during background operations.

### Security tests
Test invalid paths, malformed fixtures where safe, playlist input, untrusted metadata, network input when introduced, update integrity, and resource cleanup.

### Packaging tests
On later release milestones, test clean installation, upgrade, repair, uninstall, file association behavior, and playback without developer tools installed.

Never fabricate a successful test or performance figure. Mark unsupported and untested behavior explicitly.

---

## 11. Privacy and Security Requirements

- Local playback must work without creating an account.
- Do not upload media or library metadata by default.
- Do not enable telemetry by default.
- Explain optional network and AI processing before activation.
- Keep permissions and filesystem access limited to user-selected needs.
- Treat media, subtitles, playlists, and streams as untrusted.
- Avoid arbitrary command execution and unsafe shell interpolation.
- Keep secrets out of source control and logs.
- Use secure update verification.
- Provide clear history/library deletion controls.
- Review privacy and security impact whenever a new integration is added.

---

## 12. Definition of Done

A milestone is done only when:
- Its stated functionality is implemented or a blocker is explicitly approved.
- Acceptance criteria have evidence.
- Automated tests have been run and results recorded.
- No hidden or fabricated results are present.
- Documentation and known limitations are updated.
- License/security/privacy implications are reviewed.
- Changes are preserved in Git and reviewed.
- The milestone report is accepted before work proceeds.

A milestone can be conditionally accepted only when remaining work is clearly listed, risk is understood, and the next milestone does not depend on unresolved critical work.

---

## 13. M1 Required Deliverables

The first Codex implementation task must produce, where feasible:

- `docs/milestones/M1/environment-report.md`
- `docs/milestones/M1/benchmark-report.md`
- `docs/milestones/M1/licensing-report.md`
- `docs/milestones/M1/acceptance-report.md`
- `docs/decisions/ADR-0001-playback-engine.md`

It should also create the minimal desktop shell, common playback interface, mock adapter, engine evaluation prototypes/harness, and relevant tests.

If the engine benchmark cannot be completed in the available environment, document the exact blocker, the work completed, and the smallest next action. Do not make up benchmark results.

---

## 14. M1 Codex Prompt

Copy the prompt below into Codex while its working directory is the intended `Babarify.Frame` project directory.

> Act as a senior desktop application architect, multimedia engineer, Python engineer, test engineer, and open-source licensing compliance analyst.
>
> Implement Milestone 1 of Babarify Frame, a free, privacy-focused premium-quality media player. The first target is Windows 10 and Windows 11, 64-bit. Android and iOS are planned for later milestones. The playback engine has not been selected; benchmark libVLC and mpv before recommending one.
>
> First inspect the actual repository, working tree, OS, Python versions, installed tools, available engines, and hardware capabilities. Preserve all existing work. Do not reset Git history, delete unrelated files, make destructive changes, or alter global settings without approval.
>
> Create a minimal, maintainable repository foundation, a small PySide6/Qt desktop shell if feasible, a common playback contract with typed state/media/capability/error models, and a mock adapter for unit testing. Keep UI code independent of engine-specific APIs. Do not pretend playback works until it has been demonstrated with a real engine.
>
> Create separate minimal libVLC and mpv prototypes and a reproducible benchmark harness where the environment permits. Use the same legal test media and scenarios, repeat trials, report medians and ranges, and record engine versions, machine, OS, GPU/driver, settings, and limitations. Measure startup, seek responsiveness, playback stability, CPU/memory, hardware decoding and fallback, audio/subtitle track access, cleanup, integration complexity, and packaging risks. Do not invent results. If a test is blocked, document the exact blocker.
>
> Audit direct and transitive dependencies and their licenses, including the actual libVLC plugins, mpv build/dependencies, PySide6/Qt modules, FFmpeg if used, Python packages, bundled binaries, and codec distribution considerations. Distinguish verified findings from assumptions and unresolved legal questions. Do not claim formal legal clearance or publish a production installer.
>
> Add appropriate unit tests for state transitions, command validation, capability reporting, error mapping, mock adapter behavior, and cleanup. Add integration/smoke tests where feasible. Run tests and static checks, record actual output, and document failures or skips.
>
> Produce `docs/milestones/M1/environment-report.md`, `benchmark-report.md`, `licensing-report.md`, and `acceptance-report.md`, plus `docs/decisions/ADR-0001-playback-engine.md`. Include setup instructions, architecture documentation, known limitations, and the next recommended action.
>
> M1 is complete only if the desktop shell starts and closes cleanly, the common contract and mock tests work, engine evaluation is evidenced or blocked honestly, license risks are documented, and every acceptance criterion is marked PASS, CONDITIONAL, FAIL, or BLOCKED with evidence. Do not begin M2 or add unrequested features. Finish with a concise report of files changed, commands run, tests passed/failed/skipped, real benchmark results, risks, and recommended next steps.

---

## 15. Official Milestone Tracker

Use the following checklist as the project status source of truth. Mark a milestone complete only after reviewing its evidence and acceptance report.

- [x] M1 — Feasibility and Architecture — **CONDITIONAL**, accepted by the owner 2026-10-27 ([report](docs/milestones/M1/acceptance-report.md))
- [x] M2 — Real Playback Prototype — **PASS**, accepted by the owner 2026-10-27 ([report](docs/milestones/M2/acceptance-report.md))
- [x] M3 — Premium UI Foundation — **CONDITIONAL**, accepted by the owner 2026-10-27 ([report](docs/milestones/M3/acceptance-report.md))
- [x] M4 — Playback Reliability and Performance — **PASS**, accepted by the owner 2026-10-27 ([report](docs/milestones/M4/acceptance-report.md))
- [x] M5 — Audio and Subtitle Studio — **CONDITIONAL**, accepted by the owner 2026-10-31 ([report](docs/milestones/M5/acceptance-report.md))
- [x] M6 — Media Library and Personal History — **PASS**, accepted by the owner 2026-10-31 ([report](docs/milestones/M6/acceptance-report.md))
- [x] M7 — Picture and Audio Enhancement — **PASS**, accepted by the owner 2026-11-01 ([report](docs/milestones/M7/acceptance-report.md))
- [x] M8 — Advanced Media and Network Features — **PASS**, accepted by the owner 2026-11-01 ([report](docs/milestones/M8/acceptance-report.md))
- [x] M9 — Intelligent and Optional AI Features — **PASS**, accepted by the owner 2026-11-01 ([report](docs/milestones/M9/acceptance-report.md))
- [x] M10 — Windows Packaging, Security, and Release — **PASS**, accepted by the owner 2026-11-01 ([report](docs/milestones/M10/acceptance-report.md))
- [~] M11 — Public Beta and User Feedback — **CONDITIONAL**, accepted by the owner 2026-11-01: beta 0.9.1 prepared; PASS once the beta has run ([report](docs/milestones/M11/acceptance-report.md))
- [ ] M12 — Android Feasibility and Shared Architecture
- [ ] M13 — Android Implementation
- [ ] M14 — iOS Feasibility and Shared Architecture
- [ ] M15 — iOS Implementation
- [ ] M16 — Ongoing Maintenance and Expansion

### Current status

**Project planning baseline:** Defined in this document.  
**Implementation status:** M1 accepted as CONDITIONAL, M2 as PASS, M3 as CONDITIONAL, M4 as PASS (2026-10-27), M5 as CONDITIONAL, M6 as PASS (2026-10-31), M7 as PASS (2026-11-01), M8 as PASS (2026-11-01), M9 as PASS (2026-11-01), M10 as PASS (2026-11-01), M11 as CONDITIONAL (2026-11-01, beta prepared). Playback engine: libVLC, provisional ([ADR-0001](docs/decisions/ADR-0001-playback-engine.md)).  
**Next action:** run the 0.9.1 beta (owner actions in the [M11 report](docs/milestones/M11/acceptance-report.md) §5), triage feedback with `tools/triage_summary.py`, then decide M11 PASS and the 1.0 release from that evidence. Open from M5: committed subtitle render check (`tools/subtitle_render_check.py`).

---

## 16. Final Product Direction

Babarify Frame will be developed as a reliable, attractive, free media player with a modular playback architecture. The project will begin with a Windows prototype, compare libVLC and mpv using evidence, and then deliver playback, interface, reliability, subtitles, library, and enhancement features in sequence. Android and iOS will follow dedicated feasibility milestones.

The guiding rule remains:

**Build the foundation correctly, prove each capability, and expand only when the evidence supports it.**
