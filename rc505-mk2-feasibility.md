# Feasibility: Extending westlicht/rc505-editor for RC-505 mk2 Support

## Executive Summary

Extending the [westlicht/rc505-editor](https://github.com/westlicht/rc505-editor) to support the RC-505 mk2 is **technically feasible but requires a complete data model rewrite and a significant reverse-engineering effort**. Analysis of an actual mk2 `MEMORY001A.RC0` dump reveals that Roland adopted a radically different XML format: **all property names are replaced with single-letter positional tags** (`<A>`, `<B>`, `<C>`, ...), the effects are stored in separate top-level elements (`<ifx>`, `<tfx>`), and there are 6 tracks instead of 5. The best path forward is to fork the editor, reuse its JUCE UI shell and generic property system, and build the mk2 data model from scratch using the [Parameter Guide](https://files.kraftmusic.com/media/ownersmanual/Boss_RC-505mkII_Parameter_Guide.pdf) as the Rosetta Stone for mapping positional XML tags to human-readable parameter names.

---

## 1. What the Existing Editor Does

The westlicht/rc505-editor is a GPLv3 C++11 desktop application built on the JUCE framework. It operates on the RC-505's USB mass storage filesystem, reading and writing:

- **`ROLAND/DATA/MEMORY.RC0`** — XML file with all 99 patch definitions
- **`ROLAND/DATA/SYSTEM.RC0`** — XML file with global system settings
- **`ROLAND/WAVE/{patch}_{track}/`** — WAV audio files (44.1 kHz, 16-bit, stereo)

Key architectural components:
- **Hierarchical property system** (`Property`, `Group`, `BoolProperty`, `IntProperty`, `EnumProperty`) with XML serialization and observer/listener pattern for UI binding
- **JUCE-based GUI** with tree views, waveform displays, and drag-and-drop
- **Audio engine** using JUCE + libsamplerate + Rubber Band for playback with tempo sync
- **Multi-document interface** supporting multiple libraries simultaneously

The editor hardcodes `revision="2"` and `name="RC-505"` in the XML root, and all ~1,742 lines of `RC505.h` define the original RC-505's exact parameter set with descriptive XML tag names like `PlyLvl`, `TmpSync`, `DubMod`.

---

## 2. The mk2 RC0 Format: Analysis of Actual Data

Analysis based on [MEMORY001A.RC0](https://gist.githubusercontent.com/liotier/08f0b33abf8962533ac9b6beef2d1721/raw/c458e85b79456edebd42ef4609ce5acf9035ca05/MEMORY001A.RC0) — a single-memory-slot dump from an RC-505 mk2 (25,516 lines).

### 2.1 Top-Level Structure

```xml
<?xml version="1.0" encoding="utf-8"?>
<database name="RC-505MK2" revision="0">
  <mem id="0">    <!-- Lines 3-937: Memory settings (935 lines) -->
    ...
  </mem>
  <ifx id="0">    <!-- Lines 938-13106: Input FX definitions (12,169 lines) -->
    ...
  </ifx>
  <tfx id="0">    <!-- Lines 13107-25515: Track FX definitions (12,409 lines) -->
    ...
  </tfx>
</database>
<count>0003</count>   <!-- Binary footer/checksum outside XML -->
```

**Three separate top-level elements per memory** — the original RC-505 stores everything in a single `<mem>` element. The mk2 splits memory settings (`<mem>`), input effects (`<ifx>`), and track effects (`<tfx>`) into sibling elements with matching `id` attributes. A full 99-memory file would contain 297 top-level elements.

The `<count>0003</count>` footer after `</database>` confirms the RC0 format includes non-XML trailer data (count of top-level sections: 3 = mem + ifx + tfx).

### 2.2 Obfuscated Tag Names

The most significant format change: **all child element names within sections are replaced by sequential single letters**.

Original RC-505 (descriptive):
```xml
<TRACK1>
  <Rev>0</Rev>
  <PlyLvl>50</PlyLvl>
  <Pan>50</Pan>
  <TmpSync>1</TmpSync>
</TRACK1>
```

RC-505 mk2 (positional):
```xml
<TRACK1>
  <A>0</A>      <!-- REVERSE -->
  <B>0</B>      <!-- 1SHOT -->
  <C>50</C>     <!-- PAN -->
  <D>100</D>    <!-- PLAY LEVEL -->
  ...
  <Y>2</Y>
</TRACK1>
```

This means **parsing the mk2 format requires a positional mapping table** — you must know that `<A>` in a `<TRACK>` section means REVERSE, `<B>` means 1SHOT, etc. The [Parameter Guide PDF](https://files.kraftmusic.com/media/ownersmanual/Boss_RC-505mkII_Parameter_Guide.pdf) lists parameters in the same order as they appear in the XML, making it the essential decoding reference.

### 2.3 Complete Section Inventory

#### Inside `<mem>` (99 unique section names):

| Section | Child Tags | Purpose |
|---------|------------|---------|
| `NAME` | A-L (12) | Patch name as ASCII character codes |
| `TRACK1` through `TRACK6` | A-Y (25 each) | Per-track settings |
| `MASTER` | A-D (4) | Tempo and master settings |
| `REC` | A-F (6) | Recording options |
| `PLAY` | A-H (8) | Playback options |
| `RHYTHM` | A-M (13) | Rhythm settings |
| `ICTL1_TRACK1_FX` through `ICTL2_TRACK5_TRACK` | A-C (3 each) | Internal control targets (20 sections) |
| `ICTL1_PEDAL1` through `ICTL3_PEDAL9` | A-C (3 each) | Internal control pedal mappings (27 sections) |
| `ECTL_CTL1` through `ECTL_EXP2` | A-D/E (4-5 each) | External control mappings (6 sections) |
| `ASSIGN1` through `ASSIGN17` | A-J (10 each) | Assignable controls |
| `INPUT` | A-M (13) | Input configuration |
| `OUTPUT` | A-D (4) | Output configuration |
| `ROUTING` | A-S (19) | Signal routing matrix |
| `MIXER` | A-V (22) | Level mixer |
| `EQ_MIC1` through `EQ_SUBOUT2R` | A-L (12 each) | Per-channel parametric EQ (12 sections) |
| `MASTER_FX` | A-C (3) | Master effects (comp/reverb) |
| `FIXED_VALUE` | A-B (2) | Fixed internal values |
| `SETUP` | A (1) | Memory-level setup |

#### Inside `<ifx>` and `<tfx>` (Input FX / Track FX):

Each contains a `<SETUP>` header, then **4 FX banks** (`<A>` through `<D>`), each bank containing **4 slots** (`<AA>` through `<AD>` for bank A, `<BA>` through `<BD>` for bank B, etc.), and **each slot storing parameters for all 70 effect types** as separate sections:

```
<ifx id="0">
  <SETUP><A>0</A></SETUP>
  <A>                          ← Bank A header (3 values: mode, sw, FX target)
    <A>1</A><B>1</B><C>3</C>
  </A>
  <AA>                         ← Bank A, Slot A header (4 values)
    <A>0</A><B>0</B><C>0</C><D>0</D>
  </AA>
  <AA_LPF>                     ← Bank A, Slot A, LPF parameters
    <A>3</A><B>50</B><C>50</C><D>50</D><E>0</E>
  </AA_LPF>
  <AA_LPF_SEQ>                 ← Bank A, Slot A, LPF step sequencer (22 values)
    <A>0</A>...<V>0</V>
  </AA_LPF_SEQ>
  <AA_BPF>...</AA_BPF>
  <AA_BPF_SEQ>...</AA_BPF_SEQ>
  ... (70 effect types × {params + seq} per slot)
  <AB>...</AB>                 ← Bank A, Slot B
  ... (repeat for all 4 slots)
  <B>...</B>                   ← Bank B header
  ... (repeat for all 4 banks)
</ifx>
```

**70 unique FX types** per slot (common to both ifx and tfx):
LPF, BPF, HPF, PHASER, FLANGER, SYNTH, LOFI, RADIO, RING_MODULATOR, G2B, SUSTAINER, AUTO_RIFF, SLOW_GEAR, TRANSPOSE, PITCH_BEND, ROBOT, ELECTRIC, HARMONIST_MANUAL, HARMONIST_AUTO, VOCODER, OSC_VOCODER, OSC_BOT, PREAMP, DIST, DYNAMICS, EQ, ISOLATOR, OCTAVE, AUTO_PAN, MANUAL_PAN, STEREO_ENHANCE, TREMOLO, VIBRATO, PATTERN_SLICER, STEP_SLICER, DELAY, PANNING_DELAY, REVERSE_DELAY, MOD_DELAY, TAPE_ECHO, TAPE_ECHO_V505V2, GRANULAR_DELAY, WARP, TWIST, ROLL, ROLL_V505V2, FREEZE, CHORUS, REVERB, GATE_REVERB, REVERSE_REVERB

**`tfx` has 4 additional types** not in `ifx`: BEAT_SCATTER, BEAT_REPEAT, BEAT_SHIFT, VINYL_FLICK

Most effects also have a `_SEQ` companion section (22 values: step sequencer parameters).

### 2.4 Decoded TRACK Parameters (A-Y → Parameter Guide Mapping)

Cross-referencing the mk2 Parameter Guide with the XML positions:

| XML Tag | Value in dump | Parameter | Notes |
|---------|---------------|-----------|-------|
| A | 0 | REVERSE | OFF/ON |
| B | 0 | 1SHOT | OFF/ON |
| C | 50 | PAN | 0=L50, 50=CENTER, 100=R50 |
| D | 100 | PLAY LEVEL | 0-200 |
| E | 0 | START MODE | 0=IMMEDIATE, 1=FADE |
| F | 0 | STOP MODE | 0=IMMEDIATE, 1=FADE, 2=LOOP |
| G | 0 | DUB MODE | 0=OVERDUB, 1=REPLACE1, 2=REPLACE2 |
| H | 1 | FX | 0=OFF, 1=ON |
| I | 0 | PLAY MODE | 0=MULTI, 1=SINGLE |
| J | 1 | MEASURE | 0=AUTO, 1=FREE, 2+=measures |
| K | 0 | LOOP SYNC | OFF/ON |
| L | 1 | TEMPO SYNC SW | OFF/ON |
| M | 1 | TEMPO SYNC MODE | 0=PITCH, 1=XFADE |
| N | 1 | TEMPO SYNC SPEED | 0=HALF, 1=NORMAL, 2=DOUBLE |
| O | 1 | BOUNCE IN | OFF/ON |
| P | 0 | INPUT (low byte?) | Input routing |
| Q | 127 | INPUT (bitmask) | 0b1111111 = all 7 inputs enabled |
| R | 1 | (unknown) | |
| S | 0 | (unknown) | |
| T | 0 | (unknown) | |
| U | 1200 | Recording tempo | BPM × 10 (120.0 BPM) |
| V | 88200 | Wave length | Samples (= 2.0 sec at 44.1kHz) |
| W | 0 | Wave status | |
| X | 0 | (unknown) | |
| Y | 2 | (unknown) | |

### 2.5 Key Format Differences Summary

| Aspect | Original RC-505 | RC-505 mk2 |
|--------|----------------|-------------|
| **DB root** | `name="RC-505" revision="2"` | `name="RC-505MK2" revision="0"` |
| **Tag naming** | Descriptive (`PlyLvl`, `TmpSync`) | **Positional single letters** (`<A>`, `<B>`, `<C>`, ...) |
| **Data files** | `MEMORY.RC0`, `SYSTEM.RC0` | `MEMORY001A.RC0`+ others |
| **Top-level per memory** | 1 element (`<mem>`) | **3 elements** (`<mem>`, `<ifx>`, `<tfx>`) |
| **Tracks** | 5 (`TRACK1`-`TRACK5`) | **6** (`TRACK1`-`TRACK6`) |
| **Track params** | 10 + hidden | **25** (A through Y) |
| **Master params** | 6 (Lvl, Tmp, Cs, Rv, PhOut, PhOutTr) | **4** (separate REC + PLAY sections) |
| **Assigns** | 16 | **17** |
| **Assign params** | 6 (Sw, Src, SrcMod, Tgt, TgtMin, TgtMax) | **10** (A through J) |
| **FX architecture** | 3 slots, single/multi mode, FX params inline in `<mem>` | **4 banks × 4 slots, in separate `<ifx>`/`<tfx>` elements** |
| **FX types (input)** | 27 | **70** (including `_SEQ` variants) |
| **FX types (track)** | 31 | **74** (70 + BEAT_SCATTER/REPEAT/SHIFT + VINYL_FLICK) |
| **Per-channel EQ** | None | **12 sections** (MIC1/2, INST1L/R, INST2L/R, MAINOUTL/R, SUBOUT1L/R, SUBOUT2L/R) |
| **Routing** | None (fixed) | **19 routing parameters** |
| **Mixer** | None (track sliders only) | **22 mixer parameters** |
| **Internal controls** | None | **ICTL1/2/3 × TRACK(5) + PEDAL(9)** = 47 sections |
| **External controls** | None | **CTL1-4, EXP1-2** = 6 sections |
| **Step sequencer** | None | **Per-effect 22-value sequencer** |
| **File footer** | None | `<count>NNNN</count>` after `</database>` |
| **Lines per memory** | ~860 | **~25,500** |

---

## 3. What Can Be Reused

| Component | Reusability | Notes |
|-----------|-------------|-------|
| **JUCE application shell** | High | Main window, menu system, multi-document panel |
| **Property system base classes** | High | `Property`, `Group`, `BoolProperty`, `IntProperty`, `EnumProperty` — type system and observer pattern are generic |
| **PropertyTreeView / PropertyView** | High | Generic hierarchical property editor |
| **WaveformView** | High | Waveform display and drag-and-drop |
| **PatchTreeView** | High | 99-patch browser with reordering |
| **AudioEngine / LooperEngine** | Medium | Needs 32-bit float support and new tempo model |
| **CustomLookAndFeel** | High | Pure cosmetic, fully reusable |
| **XML I/O scaffolding** | Low | The `<mem>` / `<ifx>` / `<tfx>` split and positional tags require a new parser |
| **RC505.h data model** | **None** | Every property definition must be rebuilt from scratch |
| **RC505.cpp type defs** | **None** | All enum arrays, value ranges, type converters need replacing |

Rough estimate: **~30% of the codebase is reusable** (UI shell, property system, audio). The remaining **~70%** requires a rewrite or new implementation (data model, FX architecture, XML parser, mixer/routing/EQ subsystems that didn't exist before).

---

## 4. The Reverse-Engineering Challenge

### 4.1 The Positional Tag Mapping Problem

The mk2's single-letter tags create a **mapping table dependency**: for every XML section, you need a separate lookup that says "tag A = REVERSE, tag B = 1SHOT, tag C = PAN, ..." within `<TRACK>`, but "tag A = TEMPO, tag B = MEASURE_LENGTH, ..." within `<MASTER>`.

The [RC-505mkII Parameter Guide](https://files.kraftmusic.com/media/ownersmanual/Boss_RC-505mkII_Parameter_Guide.pdf) (44 pages) is the primary decoding reference. It lists parameters in the same order they appear in the XML. This is sufficient for the settings sections (TRACK, MASTER, REC, PLAY, RHYTHM, ASSIGN, INPUT, OUTPUT).

For the **70 FX types and their parameters**, the Parameter Guide's "Input FX/Track FX List" (pages 33-41) documents each effect's parameters and their value ranges, which can be mapped positionally to the XML child tags.

### 4.2 What Remains Unknown

Even with the Parameter Guide, these aspects need empirical verification from device dumps:
- Exact semantics of TRACK tags P-T and W-Y (likely input routing bitmasks and internal state)
- The `ROUTING` section's 19 parameters (not fully documented in the Parameter Guide)
- The `ICTL1/2/3_*` sections (internal control linkages, 47 sections × 3 params each)
- The `FIXED_VALUE` section's purpose
- Whether `TRACK6` is a real user track or an internal bus
- The exact binary format of the `<count>` footer
- Full 99-memory file structure (does each memory have its own `<ifx>` and `<tfx>`, or are they shared?)
- `SYSTEM.RC0` structure (no dump available yet)
- WAV file format details (32-bit float confirmed by rc600editor; 512 KB padding structure unknown)

### 4.3 Getting a Complete Dump

The single-memory dump is invaluable but a **full 99-memory + system dump from your own device** would resolve most unknowns. The ideal dump includes:
1. `ROLAND/DATA/MEMORY*.RC0` — all memory files
2. `ROLAND/DATA/SYSTEM*.RC0` — system settings
3. `ROLAND/DATA/RHYTHM*.RC0` — user rhythm data (if present)
4. At least one `ROLAND/WAVE/` directory with an actual WAV file (for format verification)
5. A dump with at least one non-default memory (one where you've changed settings/recorded a loop) to see which values differ from defaults

---

## 5. Approach Recommendation

### The Hybrid Path: westlicht UI + RC-500 data architecture + mk2 format

Neither existing editor is directly extendable to the mk2:
- **westlicht/rc505-editor**: Strong UI (JUCE), but its hardcoded C++ property model cannot handle the mk2's positional tags or split `<mem>`/`<ifx>`/`<tfx>` structure.
- **dfleury2/boss-rc500-editor**: Better data architecture (JSON intermediate, Inja templates), but uses Qt (not JUCE) and targets a 2-track device.

The recommended approach:

1. **Fork westlicht/rc505-editor** for the JUCE UI shell, property system, audio engine, and look-and-feel.
2. **Adopt the RC-500 editor's data architecture pattern**: Parse XML into a JSON intermediate representation using positional mapping tables, then use templates for serialization back to XML. This is far more maintainable than hardcoding 25,000+ lines of property definitions in C++.
3. **Build the mk2 data model as mapping tables** rather than C++ class hierarchies:
   - A JSON/YAML schema file defining each section's tag-to-parameter mapping, value ranges, and display types
   - A generic parser that reads the schema and the RC0 file, producing an in-memory property tree
   - Template-based serialization for writing back
4. **Decode the format incrementally**: Start with the well-understood sections (TRACK, MASTER, REC, PLAY, RHYTHM, NAME) and add FX support progressively.

### Phased Implementation

| Phase | Scope | Prerequisite |
|-------|-------|-------------|
| **1: Format mapping** | Complete positional tag → parameter mapping for all `<mem>` sections using Parameter Guide | Parameter Guide (available) |
| **2: Core editor** | Read/write memory settings (no FX). Patch browser, name editor, track/master/rec/play/rhythm settings | Phase 1 + full device dump |
| **3: FX support** | Input FX and Track FX editing (70+ types × 4 banks × 4 slots) | Phase 2 |
| **4: Audio** | WAV import/export with correct format (32-bit float, padding) | WAV file samples from device |
| **5: System settings** | System.RC0 editing | System dump |
| **6: Advanced** | Mixer, routing, EQ, step sequencer editing, playback engine | Phases 2-5 |

---

## 6. Existing Community Landscape

| Tool | Device | Open Source | Status |
|------|--------|------------|--------|
| [westlicht/rc505-editor](https://github.com/westlicht/rc505-editor) | RC-505 (original) | Yes (GPLv3) | Beta, unmaintained since 2019 |
| [rc600editor.com](https://rc600editor.com/) | RC-505 mk2, RC-600 | No (commercial) | Active, paid ($15) |
| [dfleury2/boss-rc500-editor](https://github.com/dfleury2/boss-rc500-editor) | RC-500 | Yes (MIT) | Active |
| BOSS Tone Studio | RC-505 mk2 | No (official) | Backup/restore only, no editing |

There is currently **no open-source editor for the RC-505 mk2**. The rc600editor.com developer has noted that "the RC-505mk2 uses different nodes than the RC-600 for the same controls in its assigns source and target values" — confirming that even between the two newest-generation devices, the positional mappings differ.

---

## 7. Conclusion

The mk2's format is **more different from the original RC-505 than initially expected**. The shift to positional single-letter tags, the 3-element-per-memory structure, and the 30× increase in per-memory data (860 → 25,500 lines) mean this is not a "remap the tag names" exercise — it's a fundamentally different data architecture that requires a new parser, new mapping tables, and a new serialization strategy.

However, the format is **regular and predictable**: sections are cleanly separated, values are plain integers, the FX structure is systematically repeated across all banks/slots, and the Parameter Guide provides the mapping key. An editor built on data-driven mapping tables (rather than hardcoded C++ property classes) could support the mk2 with a manageable schema file, and could later be extended to other Boss loopers by swapping schemas.

**Next step**: Obtain a full device dump (all RC0 files + at least one WAV) from your RC-505 mk2 to complete the format mapping and begin implementation.
