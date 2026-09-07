Verified campaign UI facts. Position and log truth beat colour and guesswork.

- CONTROL: The End Turn control is the round button at the far bottom-right of the client area, centred at (0.980, 0.971).
- CONTROL: Parchment panels are closed by a round button bearing a gold crossed-swords X, centred ON the panel's top-right corner (straddling the panel edge, not inside it).
- INPUT: Escape closes some panels and is ignored by others — the settlement/building browser stayed open through 40+ Escape presses.
- SEMANTICS: A blocking panel with no close X is not a detector failure — it is how the game says "you must answer this".
- GROUND_TRUTH: Do not invent names for panels.
- LAYOUT: The Diplomatic Negotiations panel is three scrolls in one — faction heir left, the negotiation centre, the diplomat right — so its measured span (x 0.20-0.76, top y 0.13) is wider than the centre scroll alone.
- HAZARD: The Battle Deployment panel (SMT_BATTLE_DEPLOYMENT, x 0.16-0.83, top y 0.35) is where the campaign hands over to the battle map.
- SEMANTICS: A panel being open does not mean the game is blocked.
- GROUND_TRUTH: Screen state never proves a turn ended.
- GROUND_TRUTH: message_log.txt is not a dependable channel.
- GROUND_TRUTH: The saves folder is the reliable turn clock, and it distinguishes two events that must not be confused.
- HAZARD: Clicking unverified positions in the lower-right lands on the map or HUD and mutates game state.
- LAYOUT: The Event Log is one parchment, not four windows.
- SEMANTICS: Each campaign question has one authoritative surface.
- LAYOUT: The settlement building browser spans x 0.26-0.74 with its top edge near y 0.21, and covers the bottom-right HUD including the End Turn control.
- PERCEPTION: Winter and night cameras render the map dim and nearly flat: centre luminance around 0.15 with low variance, while the HUD edges stay near 0.30.
- PERCEPTION: Screenshots must cover the client rect.
