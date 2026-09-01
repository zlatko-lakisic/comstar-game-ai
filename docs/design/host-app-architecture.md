# Host app architecture (Windows)

The local application that observes and drives Rome Remastered and talks to AO over Reach. Written 2026-09-01. Companion to `rtw-remastered-integration.md` and `decisions.md`.

## 1. The reframing: capture speed is not the bottleneck

The instinct to reach for DirectX is right, but the constraint is not where it feels like it is.

Fast capture on Windows is a solved problem. [DXcam](https://github.com/ra1nty/DXcam) benchmarks at roughly 239 fps on the Desktop Duplication API against 76 for python-mss and 118 for D3DShot, it captures arbitrary regions, and it has an optional Windows Graphics Capture backend. Capture is cheap and available.

What is not cheap is everything after it. Reach caps a turn at 16 images, 4 MiB each, 20 MiB total, and vision inference costs seconds. You physically cannot stream video to the model, and the cap is enforcing the correct architecture rather than getting in the way.

So the design problem is **frame selection, not frame rate**.

Fast capture still earns its place, for a different reason than raw throughput. Keep a rolling ring buffer of the last few seconds at high rate. When the battle is unfrozen for three seconds and something happens, being able to look *backwards* and pick the two frames that show the moment of contact is worth far more than being able to send thirty. Capture fast, retain briefly, select few, send fewer.

## 2. Capture: the hard constraint is the game's display mode

**The game must run borderless windowed. Never exclusive fullscreen.**

This is not a preference. Microsoft's own guidance is that Windows Graphics Capture is not guaranteed to capture exclusive fullscreen applications, because in that mode the game may present directly to the display and bypass DWM composition, leaving no composed surface to capture. Behaviour varies by application, graphics API, driver and Windows version, which is the worst possible failure mode: intermittent. Borderless windowed keeps the game inside normal composition and capture works reliably.

Treat this as a startup precondition the app verifies and refuses to run without, not as documentation someone might read.

> **Revised 2026-09-01.** The on screen overlay decision moved the primary capture path to **WGC window capture of the game window**. The deciding reason is not the overlay: Desktop Duplication captures the whole monitor, so Windows toasts, the Steam overlay and Discord popups all land in frames, and none of them can be excluded by display affinity because they are not our windows. See `host-overlay-ui.md` section 1.

| Approach | Verdict |
|----------|---------|
| Windows Graphics Capture, window targeted | **Primary.** Captures the game window's own content, so anything drawn on top is structurally excluded. Windows 10 1803 and later. |
| Desktop Duplication (DXGI) | Superseded as primary. Simplest path and best library support, but it captures everything on the monitor including other applications' overlays. |
| GDI / BitBlt | Rejected. Slow and unreliable against hardware accelerated rendering. |
| DirectX hooking or injection | **Rejected on principle.** Fastest option, and how OBS game capture works, but it means injecting into the game process. That contradicts the boundary set in the integration document, which is what keeps this project clear of EULA and anti tamper questions. Not worth it for a single player agent when borderless plus Desktop Duplication is already fast enough. |

## 3. Input: SendInput, and its silent failure mode

`SendInput` is the mechanism. Its documented limitations are architectural rather than incidental, and two of them shape the whole design.

**UIPI blocks injection into higher integrity processes, and the failure is silent.** Microsoft state plainly that neither the return value nor `GetLastError` indicates that UIPI caused the failure. So the app and the game must run at the same integrity level, checked at startup, and more importantly: **you can never learn from the API whether an action landed.**

That single property forces the actuation model. Every action is a closed loop:

```
declare intent -> execute -> verify by observation -> retry or escalate
```

Not fire and forget. Verification comes from the structured channels where one exists, meaning a log line or a console query confirming the state changed, and from vision where none does. An action that cannot be verified is an action you do not know happened.

This is also an independent argument for the intent record recommended in `decisions.md` C5. Silent actuation failure is not a hypothetical here, it is a documented property of the API this app is built on.

The other documented limits worth designing around:

- `SendInput` returns zero if another thread has already blocked the input stream.
- It does not reset keyboard state, and keys already held when it is called can interfere with the events it generates. Check with `GetAsyncKeyState` and normalise before every action sequence.
- Events are inserted serially and are not interspersed with other input, so genuine user input and injected input cannot collide mid sequence, but they can still interleave between sequences.
- Injection follows focus, so the game must be the foreground window. The machine is dedicated while the agent plays.

Two more that are not in that page but will bite:

- Absolute mouse positioning is normalised across the virtual desktop, so multi monitor and mixed DPI setups need an explicit, tested coordinate transform rather than an assumed one.
- Games poll input and need hover states to register. Teleport and instant click will be missed. Movements need dwell and intermediate steps, for reliability rather than for disguise.

## 4. Two processes, and why not one

```
  ┌─────────────────────────────────────┐
  │  Process A: Game I/O service        │   small, boring, hard to break
  │                                     │
  │  capture ring buffer                │
  │  frame selector                     │
  │  SendInput actuator                 │
  │  console channel (RomeShell)        │
  │  log tailers                        │
  │  window + focus watchdog            │
  │  KILL SWITCH + interlocks           │
  └──────────────┬──────────────────────┘
                 │ local IPC, shared memory for frames
  ┌──────────────┴──────────────────────┐
  │  Process B: Agent runtime           │   heavy, allowed to stall
  │                                     │
  │  belief store                       │
  │  abstract simulator + search        │
  │  intent log                         │
  │  Reach client -> AO                 │
  └─────────────────────────────────────┘
```

The split exists for one reason: **a stalled agent must not leave keys held down.** If belief, search and a Reach round trip live in the same process as the actuator, then a hung deliberation or a garbage collection pause can freeze mid drag with the mouse button down. Splitting them means Process A can always release input, honour the kill switch, and act on the dead man's timer regardless of what Process B is doing.

## 5. The safety layer, which is not optional

This app takes complete control of the mouse and keyboard on a machine you are sitting at. That needs four things, all in Process A:

1. **Global kill hotkey** on a dedicated thread that releases all held keys and buttons and halts actuation immediately.
2. **Dead man's switch.** If Process B has not sent a heartbeat within N seconds, release input and stop.
3. **Human override.** Physical mouse movement or keypress suspends the agent immediately. The human always wins a conflict.
4. **Release on every exit path**, including crash and unhandled exception. A held mouse button surviving a crash is the failure everyone experiences once and never forgets.

Worth stating because it is easy to leave until later and genuinely unpleasant to discover you needed.

## 6. The Reach boundary

You said all communication goes through Reach to AO. That is right for agent communication and wrong for the control loop, and the distinction matters.

**Why the control loop cannot go through Reach.** A Reach round trip is seconds. A campaign turn is tens of actions. A twenty minute battle at a three second tick is several hundred decision points. Round tripping each one is not playable. The image caps make the same point from the other direction: 16 images and 20 MiB per turn means streaming was never on the table.

**So the split is hierarchical.** AO decides *what*, the local app decides *how*.

| Direction | Mechanism | Carries |
|-----------|-----------|---------|
| App to AO | `direct_agent` with belief brief plus selected frames | The situation and the question |
| AO to app | Reverse MCP tunnel, `client.game_query` | Pull requests for detail the brief omitted |
| AO to app | Run result | The directive: posture, objective weights, priors, commentary |
| Inside the app | Local, never Reach | Belief updates, search, action sequencing, verification |

The tunnel is the elegant part and the reason the brief can stay inside budget. Rather than pushing everything the agent might want, the app exposes tools like history lookup, unit detail and per faction belief, and the agent pulls only what it decides it needs. That is `SessionMcpBootstrap` and `LocalMcpHost` doing exactly what they were designed for.

The one line version: **Reach carries intent and belief, not pixels and clicks.**

## 7. Runtime choice

Python for both processes is the pragmatic start. The `ao_reach` Python package already exists and is protocol compatible, and it carries the pieces this needs, meaning images, priority, cancel, mTLS, catalog and the tunnel responder. DXcam is Python. SendInput is reachable through ctypes or pywin32. That is one language end to end and no native build step.

Two things to watch. Reach's reference implementation is Dart and Python is the port, so confirm parity for anything newly added before depending on it. And if the safety thread in Process A proves unreliable under load, that process is small and self contained enough to be rewritten in C# or Rust without touching the agent side. Do that on measurement, not on principle.

Since the AO engine runs on a different machine, Reach needs mTLS enrollment against the engine, which is the one time token flow already documented in the platform context.

## 8. Risk register

| Risk | Detection | Response |
|------|-----------|----------|
| Game launched in exclusive fullscreen | Startup precondition check | Refuse to run and say why |
| UIPI blocking injection, silently | Cannot be detected from the API | Integrity level check at startup, plus outcome verification on every action |
| Agent stalls mid drag | Dead man's timer in Process A | Release input, halt |
| Game patch moves the UI | Calibration routine fails | Pin the game version, prefer console text over pixel interaction |
| Focus lost mid sequence | Window watchdog | Abort the sequence, re verify state, resume |
| Mixed DPI or multi monitor coordinate drift | Calibration against `show_cursorstat` | Explicit transform, re calibrated per camera pose |
| Vision budget exhausted on low value frames | Per turn accounting | Frame selection policy, and the tunnel for pull based detail instead |

## 9. Open questions

- Does Rome Remastered offer a true borderless windowed mode, or only windowed and exclusive fullscreen? If only the latter two, windowed with a hidden border is the fallback and capture region needs client area offsets.
- Does the game ever require elevation? If so Process A must match it, which changes the install story.
- Dedicated monitor for the game, or shared with the app's own UI? Dedicated allows the simpler Desktop Duplication path.
- Is the AO engine reachable from the Windows box over the network, and is mTLS already enrolled for a client on it?

## Sources

- [DXcam](https://github.com/ra1nty/DXcam)
- [WGC and exclusive fullscreen capture, Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5791521/wgc-capturing-exclusive-fullscreen-games-apps)
- [SendInput function, Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- [Raw Input overview, Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input)
