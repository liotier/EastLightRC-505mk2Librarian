# Dump collection for schema gap filling

## 1. CTL FUNC map (`ctl_func_map.txt`)

Fill in the display name shown on the RC-505 MK2 screen for each integer value.
Navigate to SYSTEM > CTRL on any controller, scroll through CTL FUNC values.

Stop when the list wraps or no more entries appear.

## 2. SETUP unknown fields

**13 unknown fields: J, K, L, M, N, O, P, Q, R, S, T, U, V**

Already mapped (A-I):

| Tag | Name |
|-----|------|
| A | Current Memory |
| B | Display Mode (COLOR/MONO/SIMPLIFIED) |
| C | Memory Extent Max |
| D | Contrast |
| E | Auto Off |
| F | Indicator (TYPE1/TYPE2/OFF) |
| G | FX Knob Mode (DIRECT/TOGGLE) |
| H | Knob Function |
| I | Memory Extent Min |

No per-field dumps needed here — instead, just tell me what SYSTEM > SETUP
menu items exist beyond the ones above. The RC-505 MK2 SETUP menu should
list them. If you can give me the menu item label and which value range
it shows when you scroll, that's sufficient.

## 3. PREF unknown fields

**6 unknown fields: O, P, Q, R, S, T**

Already mapped (A-N):

| Tag | Name (all are SYSTEM/MEMORY toggles) |
|-----|------|
| A | Main Output |
| B | Sub 1 Output |
| C | Sub 2 Output |
| D | Phones Output |
| E | Rhythm |
| F | Master FX |
| G | Input |
| H | Output |
| I | Routing |
| J | Mixer |
| K | EQ |
| L | Controllers |
| M | Assign |
| N | Track Settings |

Same approach: look at the SYSTEM > PREF menu on the device and tell me
which preference items appear after "Track Settings". They should all be
SYSTEM/MEMORY toggles.
