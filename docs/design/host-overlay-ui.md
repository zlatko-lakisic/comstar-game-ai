# Host app on-screen overlay

The operator-facing overlay that runs on the game monitor. Written 2026-09-01. Companion to `host-app-architecture.md`.

Everything marked **open** is a decision awaiting an answer, per the working agreement.

## 1. The requirement that constrains the rest

The overlay lives on the same monitor as the game, and the screenshots sent to AO must contain only the game. Those two facts pull against each other, because the established capture path is Desktop Duplication, which captures the whole monitor including anything drawn on top of it.

There are two independent mechanisms that solve it, and they can be used together.

### Mechanism A: exclude the overlay from capture

`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`, value `0x00000011`. The window stays visible on the physical display and is completely absent from screen captures.

Documented constraints that matter here:

- **Windows 10 version 2004 or later.** On earlier builds the value silently degrades to `WDA_MONITOR`, which renders the window **blank** in captures rather than absent. That is worse than not excluding it at all, because a black rectangle over part of the game corrupts the frame the model sees. This makes the Windows build a hard startup precondition, not a recommendation.
- **Top level windows only, owned by the calling process.** Anything else returns FALSE. So each overlay surface is its own top level window, and the overlay process sets affinity on its own windows.
- **Requires DWM to be composing the desktop.** Already satisfied, since the borderless windowed requirement from the host app design exists for the same underlying reason.
- Microsoft state plainly this is not a security or DRM feature. Irrelevant here, since the goal is frame hygiene rather than protection.

### Mechanism B: capture the game window rather than the monitor

Windows Graphics Capture can target a specific window, and content drawn by other windows on top is structurally not included. Nothing has to opt out.

The cost is that the host app design currently recommends Desktop Duplication via DXcam, which is region based on a monitor rather than window based. Moving to window capture likely means a different capture path.

### Decided 2026-09-01: both, with window capture load bearing

**WGC window capture of the game window is the primary mechanism. `WDA_EXCLUDEFROMCAPTURE` on every overlay surface is cheap insurance on top.**

The reason window capture has to be primary is not this overlay at all.

`WDA_EXCLUDEFROMCAPTURE` can only be set on windows **owned by the calling process**. It excludes our overlay and nothing else. Desktop Duplication captures the entire monitor, which means it also captures every other thing Windows puts over a game: toast notifications, the Steam overlay, Discord popups, update prompts. None of those can be excluded by affinity, because they are not our windows. Those are not hypothetical, they appear over games constantly, and each one lands in a frame the model then reasons over.

Window capture excludes all of it structurally, because it captures the game window's own content rather than whatever happens to be on that patch of screen.

**The specific risk that makes a leak worse than it sounds.** The chat window in section 4.4 displays AO's own previous directive. If it leaked into a frame, the model would be shown its own prior output rendered as part of the game state, on every subsequent call. That is a self reinforcing loop, and it would degrade reasoning subtly rather than failing visibly, which is the worst way for a defect to behave.

Affinity stays because it costs three API calls at startup and covers the case where an overlay surface somehow lands inside a window capture. Its degradation on Windows builds before 2004 is harmless in this combination, since a blank overlay window is not in a game window capture either way.

**The cost, stated honestly.** DXcam is monitor and region based, so window capture likely means a different capture path. That is a real change to the recommendation in `host-app-architecture.md` and it should be treated as work rather than a configuration flag.

### The self test, whichever is chosen

Because this design already assumes silent failure is the normal failure, verify rather than trust. At startup, render a known test pattern into every overlay surface, take a capture through the real capture path, and assert the pattern is absent. Refuse to run if it is present.

**Built 2026-09-04** as `comstar-overlay --self-test`, which runs all three window checks against the full overlay and exits non-zero on any failure. The verdicts live in `overlay_ui/checks.py` and are unit tested against synthetic frames, including the case that matters most: a check must not pass because the overlay never appeared.

## 2. The overlay can silently break actuation, in the hardest way to diagnose

This is the most important thing on this page.

The agent drives the game with `SendInput`, which follows focus and lands wherever the pointer is. An overlay window sitting over the game can intercept both. Two window properties are therefore mandatory rather than cosmetic:

| Property | Style | If missing |
|----------|-------|-----------|
| Click through | `WS_EX_LAYERED \| WS_EX_TRANSPARENT` | Synthetic clicks land on the overlay. `SendInput` reports success. The game does nothing |
| Never activates | `WS_EX_NOACTIVATE`, plus topmost without focus | The overlay takes foreground and receives the input intended for the game |

Both failures present identically to the UIPI failure already documented, meaning the API reports success and nothing happens. That is the exact symptom the intent record in D1 exists to disambiguate, and adding an overlay creates two more ways to produce it.

**So two more startup self tests.** After showing the overlay: assert `GetForegroundWindow` is still the game, and synthesise a click at a point the overlay covers and confirm the game received it.

## 3. Process placement and the takeover handshake

**Decided 2026-09-01: a separate process, and it detects the game and asks to take over before the agent acts.**

The host app design splits Process A, game I/O, from Process B, agent runtime, on the grounds that a stalled agent must never leave keys held down. The same reasoning applies to the UI: a hung or crashed overlay must not block actuation or the kill switch.

```
Process A (game I/O)  ──┐
                        ├──> one way event stream ──> Process C (overlay UI)
Process B (agent)     ──┘
```

### The click through overlay cannot host the prompt

This is the wrinkle. Section 2 makes every overlay surface click through and non activating, which is mandatory or actuation breaks. **A window that cannot be clicked and never takes focus cannot host an interactive consent button.**

Two ways out:

| Option | Note |
|--------|------|
| **Hotkey confirmation** | The overlay displays the ask, the answer is a keypress. No focus steal, and it is symmetric with the kill switch, which is already a hotkey |
| Separate interactive window | A small ordinary window that does activate. Focus stealing is acceptable here because it happens before actuation begins, but it is a second window type to manage |

**Decided 2026-09-04: hotkey confirmation.** Same mechanism grants control and revokes it: `ctrl+shift+home` takes over, `ctrl+shift+pause` hands back, `ctrl+shift+end` kills, all registered in Process A and all configurable under `safety` in `config/default.yaml`.

### Where detection and control live

**Decided 2026-09-04: Process A detects the game and owns the control state machine. Process C displays it.**

The reasoning: the kill switch hotkey must live in A regardless, because it has to work when C is dead. The window watchdog is already an A concern. Putting takeover in A means one hotkey handler, one owner of control state, and the event stream stays one way, which keeps every path to the mouse and keyboard inside the process that owns the kill switch.

C still shows the ask. It is displaying A's state rather than owning it.

### Three control transitions, not one

The host app design only covered emergency stop. Takeover implies a fuller model:

| Transition | Trigger | Behaviour |
|------------|---------|-----------|
| **Take over** | Game detected, user confirms by hotkey | Agent begins acting |
| **Hand back** | User hotkey | Finish the current action cleanly, release input, go idle. Graceful |
| **Kill** | Kill hotkey, dead man's timer, or human touches the mouse | Release everything immediately, mid action if necessary |

Hand back and kill are different operations and should not share a key. Kill is for when something is wrong; hand back is for when you want the mouse.

### Detection

Watch for the Rome process and its main window, identified by process name plus window class or title.

**Decided 2026-09-01: takeover is offered only once the game is in a playable state, not on the main menu.**

That requirement does not stay confined to takeover. Knowing whether the game is on the campaign map, in a modal scroll, deploying, fighting, or on a loading screen is needed continuously, because every action the agent issues depends on it. The full state machine, its detection signals, and what the agent does in each state are in `rtw-remastered-integration.md`. The takeover gate is one consumer of it.

If the game window closes or loses foreground while the agent holds control, the agent stands down. That is the watchdog already in the host app design.

## 4. The four surfaces

### 4.1 Edge glow

A borderless topmost window sized to the game window, painting only an edge gradient with the interior fully transparent. Follows the game window if it moves or the resolution changes, which needs a window position watcher.

**Decided 2026-09-04: colour encodes state rather than being constant.** A static glow says the app is running. A state coloured glow says what it is doing, which is more useful at a glance and costs nothing extra. Frozen and deliberating collapsed into one state, since the battle loop freezes the game precisely in order to deliberate, leaving five:

| State | Meaning |
|-------|---------|
| Acting | Issuing orders |
| Deliberating | Battle frozen, waiting on AO |
| Suspended | Human touched the mouse, agent stood down, or control is being handed back |
| Fault | Actuation verification failed, or the kill switch fired |
| Idle | No agent control |

The colours are fixed in `overlay_ui/state.py` and match the legend in `docs/images/overlay-mockup.html`, which is the version an operator will have learned to read.

### 4.2 Cursor indicator

A ring following the pointer with a short fading trail, and a brief pulse at click points.

**Decided 2026-09-04: distinguish synthetic from human movement by colour.** The safety layer already suspends the agent when the human moves the mouse, so showing which one is driving makes that visible rather than inferred. Synthetic uses the deliberating cyan, human the idle grey.

**Decided 2026-09-04: show intent before movement.** A hollow marker at the destination, on the end of a dashed leash, drawn when the intent is declared rather than when the cursor arrives. Hollow because the click has not happened yet. This is what gives an operator time to hit the kill switch before a bad order lands, and it makes the intent record from D1 visible in real time.

**Decided 2026-09-04: twelve trail points, no time-based decay.** The trail fades by position in the queue rather than by age, so it costs one repaint per pointer event and nothing at all while the pointer is still — which is most of a frozen battle.

### 4.3 Virtual keyboard

Fades in on use, fades out after an idle period.

**Open: full QWERTY, or only the keys the agent actually uses.** Rome's agent vocabulary is small, meaning digits for control groups, Ctrl, Alt and Shift, space for pause, backtick for the console, and camera keys. A compact cluster of just those keys is far more legible at small size than a full keyboard, but a full keyboard is more immediately recognisable.

**Open:** placement, and whether held modifiers render differently from momentary taps. Held modifiers matter, since group selection depends on them.

### 4.4 Chat window, top right, translucent

**Decided 2026-09-01: it shows the full intent cycle, not only the traffic.** Request, then live status, then directive, then what the agent actually did as a result. That last element is the intent record from D1, and including it makes this the live view of the intent log rather than a network monitor.

This is what requires the event stream in section 5 to carry intent and verification events, not just input and AO traffic.

Content available without extra work:

| Line | Source |
|------|--------|
| Outbound: agent, question id, brief summary, number of composed views | Host app |
| Live status: `processing`, `phase`, and the user friendly `message` | `ReachRunStatus` via `on_status` |
| Queue position: "queued 2 of 3" | `ReachRunStatus` queue fields |
| Inbound: objective, acceptable losses, one line commentary | The directive |
| Latency, and error code on failure | `ReachRunError` |

**Open:** how many entries of scrollback, and whether the full directive is expandable or only ever summarised.

## 5. Event stream

One way, from A and B into C.

| Event | From | Drives |
|-------|------|--------|
| Pointer moved, synthetic or human | A | Cursor indicator |
| Key down, key up, with modifier state | A | Virtual keyboard |
| Intent declared | A | Ghost marker, chat window |
| Verification result | A | Fault state on the glow |
| Freeze, resume | A | Frozen state |
| AO request sent | B | Chat window |
| AO status update | B | Chat window, deliberating state |
| AO result or error | B | Chat window |
| Agent suspended or resumed | A | Suspended state |

## 6. Rendering

**Decided 2026-09-04: PySide6, frameless and translucent, with the native extended styles applied through ctypes.**

The alternatives were a C# or WPF overlay process, which buys the best native window control at the price of a second language and a build step, and a web view, which is the easiest to style and the fiddliest to make both transparent and click through. Neither price is worth paying while the whole overlay is five windows drawing a border, a chip, a key row, a cursor ring and a scrollback.

Whichever is chosen, the overlay must be cheap to redraw. In battles the game is frozen most of the time, so this matters less than it would otherwise, but campaign play runs continuously.

### 6.1 What was built, 2026-09-04

Five surfaces rather than four: the edge glow and the state chip are separate top-level windows, because the glow has to span the whole client area to frame it while the chip has to be small enough to sit in a corner without covering the map.

Three decisions had to be made without a live game to test against, and each was made in the direction that fails safe:

- **The click through self test asks the OS, it does not click.** `WindowFromPoint` honours `WS_EX_TRANSPARENT`, so asking which window owns a point *is* the click through question, and unlike injecting a real click it cannot mutate a live campaign to answer it.
- **Capture exclusion is proved, not assumed.** `--self-test` fills the client area with a colour Rome's earth-sea-parchment palette never produces, then asserts it is absent from a captured frame. The stroke-only glow of normal operation could pass that test by being too faint to detect.
- **The human override triggers ship disarmed.** Foreground loss and mouse motion are both real signals, but a false positive aborts a run in progress, and the mouse trigger cannot tell the agent's own clicks from a human's until every input path declares its synthetic moves. They are wired, tested against fake inputs, and left off in config until a live run can confirm them.

The alignment target is the **client** rect, not the window rect, matching the capture path: on the reference machine those differ by a 31 px title bar and an 8 px border, which is enough to put every surface out of register with the coordinates Process A derives from a frame.

## 7. Consequences for existing documents

- **`host-app-architecture.md` needs its capture recommendation revised.** It recommends Desktop Duplication via DXcam. Section 1 moves the primary path to WGC window capture of the game window, for reasons that turn out to have nothing to do with this overlay.
- The startup precondition list grows from one item to four: borderless windowed, capture exclusion verified by self test, overlay click through verified, and overlay non activation verified.
- The control model grows from one transition, kill, to three: take over, hand back, kill.
- Process C is added to the process model, with a one way event stream carrying input, intent, verification and AO events.

## Sources

- [SetWindowDisplayAffinity, Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)
- [SendInput, Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
