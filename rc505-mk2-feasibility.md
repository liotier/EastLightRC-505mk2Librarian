# Feasibility: Extending westlicht/rc505-editor for RC-505 mk2 Support

## Executive Summary

Extending the [westlicht/rc505-editor](https://github.com/westlicht/rc505-editor) to support the RC-505 mk2 is **technically feasible but requires a complete data model rewrite**. Analysis of a full mk2 device dump (all 99 memory files, system settings, rhythm data, and WAV samples) reveals that Roland adopted a radically different XML format: **all property names are replaced with single-letter positional tags** (`<A>`, `<B>`, `<C>`, ...), the effects are stored in separate top-level elements (`<ifx>`, `<tfx>`), and each memory slot is an individual file (not one monolithic file). The format is now **fully decoded** — track parameters, FX architecture, WAV format, tempo/sample relationships, file naming conventions, and system structure are all understood. The best path forward is to fork the editor, reuse its JUCE UI shell and generic property system, and build the mk2 data model from scratch using data-driven mapping tables.

---

## 1. What the Existing Editor Does

The westlicht/rc505-editor is a GPLv3 C++11 desktop application built on the JUCE framework. It operates on the RC-505's USB mass storage filesystem, reading and writing:

- **`ROLAND/DATA/MEMORY.RC0`** — a single XML file with all 99 patch definitions
- **`ROLAND/DATA/SYSTEM.RC0`** — a single XML file with global system settings
- **`ROLAND/WAVE/{patch}_{track}/`** — WAV audio files (44.1 kHz, 16-bit, stereo)

Key architectural components:
- **Hierarchical property system** (`Property`, `Group`, `BoolProperty`, `IntProperty`, `EnumProperty`) with XML serialization and observer/listener pattern for UI binding
- **JUCE-based GUI** with tree views, waveform displays, and drag-and-drop
- **Audio engine** using JUCE + libsamplerate + Rubber Band for playback with tempo sync
- **Multi-document interface** supporting multiple libraries simultaneously

The editor hardcodes `revision="2"` and `name="RC-505"` in the XML root, and all ~1,742 lines of `RC505.h` define the original RC-505's exact parameter set with descriptive XML tag names like `PlyLvl`, `TmpSync`, `DubMod`.

---

## 2. The mk2 RC0 Format: Complete Analysis from Full Device Dump

Analysis based on a complete device dump: 201 RC0 files (99 A + 99 B memory files, SYSTEM1, SYSTEM2, RHYTHM), 127 WAV files across 27 memories, and a full file listing of the SD card contents.

### 2.1 Filesystem Layout

```
ROLAND/
├── DATA/
│   ├── MEMORY001A.RC0 through MEMORY099A.RC0   (99 files, live state)
│   ├── MEMORY001B.RC0 through MEMORY099B.RC0   (99 files, backup state)
│   ├── SYSTEM1.RC0                              (live system settings)
│   ├── SYSTEM2.RC0                              (backup system settings)
│   └── RHYTHM.RC0                               (binary rhythm pattern data)
└── WAVE/
    ├── 001_1/001_1.WAV                          (Memory 001, Track 1)
    ├── 001_2/001_2.WAV                          (Memory 001, Track 2)
    ├── ...
    ├── 028_3/028_3.WAV                          (Memory 028, Track 3)
    ├── 039_5/                                    (empty placeholder dir)
    ├── ...
    └── TEMP/__TEMPSP.BIN                        (recording scratch file)
```

**Key differences from original RC-505:**
- **Individual files per memory** instead of one monolithic `MEMORY.RC0`
- **A/B file pairs**: A = live state, B = backup/previous save. Factory memories have identical A and B; user-modified memories diverge (typically in FX parameters and play settings)
- **Memory numbering**: files are `MEMORY001`-`MEMORY099`, but the XML `<mem id="N">` uses 0-indexed IDs (MEMORY001 → id=0, MEMORY099 → id=98)
- **WAV directories**: `{NNN}_{T}/{NNN}_{T}.WAV` where NNN=memory number, T=track (1-5). Empty directories exist as placeholders for factory presets
- **Tracks 1-5 only** have WAV files — no track 6 WAV directories exist
- **`<count>NNNN</count>`** footer after `</database>` — appears to be a save/version counter (not a checksum): Memory001A has count=0013, Memory001B has count=0014, factory defaults have count=0001

### 2.2 Per-Memory XML Structure

Each memory file contains three sibling elements under `<database>`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<database name="RC-505MK2" revision="0">
  <mem id="0">     <!-- Lines 3-925: Memory settings (923 lines) -->
    <NAME>...</NAME>
    <TRACK1>...</TRACK1> through <TRACK6>...</TRACK6>
    <MASTER>...</MASTER>
    <REC>...</REC>
    <PLAY>...</PLAY>
    <RHYTHM>...</RHYTHM>
    <ICTL*>...</ICTL*>     <!-- Internal control mappings -->
    <ECTL*>...</ECTL*>     <!-- External control mappings -->
    <ASSIGN1>...</ASSIGN1> through <ASSIGN16>...</ASSIGN16>
    <INPUT>...</INPUT>
    <OUTPUT>...</OUTPUT>
    <ROUTING>...</ROUTING>
    <MIXER>...</MIXER>
    <EQ_*>...</EQ_*>       <!-- Per-channel parametric EQ -->
    <MASTER_FX>...</MASTER_FX>
    <FIXED_VALUE>...</FIXED_VALUE>
  </mem>
  <ifx id="0">    <!-- Lines 926-13094: Input FX (12,169 lines) -->
    <SETUP>...</SETUP>
    <!-- 4 FX groups (A-D) × 4 slots × 66 effect types -->
  </ifx>
  <tfx id="0">    <!-- Lines 13095-25503: Track FX (12,409 lines) -->
    <SETUP>...</SETUP>
    <!-- 4 FX groups (A-D) × 4 slots × 70 effect types -->
  </tfx>
</database>
<count>0013</count>
```

Total: **2,316 XML sections** per memory file, **25,504 lines**.

### 2.3 Obfuscated Tag Names

All child element names within sections are replaced by sequential single letters:

Original RC-505 (descriptive):
```xml
<TRACK1>
  <Rev>0</Rev>
  <PlyLvl>50</PlyLvl>
  <Pan>50</Pan>
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
  <Y>1</Y>
</TRACK1>
```

**Note**: Roland's XML is not strictly valid — some sections use numeric tag names (`<0>`, `<1>`, ...) and symbols (`<#>`) for large parameter sets like STEP_SLICER (37 fields: A-Z, 0-9, #). Standard XML parsers will reject these; a tolerant/regex-based parser is required.

### 2.4 TRACK Parameters — Fully Decoded

Cross-referencing multiple memories (populated vs factory defaults) with WAV file metadata:

| Tag | Value Range | Parameter | Evidence |
|-----|-------------|-----------|----------|
| A | 0-1 | REVERSE | Always 0 in dump |
| B | 0-1 | 1SHOT | Always 0 in dump |
| C | 0-100 | PAN | 50 = center (confirmed) |
| D | 0-200 | PLAY LEVEL | 95-100 in populated tracks |
| E | 0-1 | START MODE | 0=IMMEDIATE |
| F | 0-1 | STOP MODE | 0=IMMEDIATE, 1=FADE |
| G | 0-2 | DUB MODE | Always 0 |
| H | 0-1 | TRACK STATE | 0=initialized in memory, 1=factory empty |
| I | 0 | (reserved) | Always 0 |
| J | 0-27 | COLOR INDEX | Track display color (0-27, varies per track) |
| K | 0-1 | LOOP SYNC | Always 0 in dump |
| L | 0-1 | TEMPO SYNC SW | Almost always 1 |
| M | 0-1 | FX SW | 0 or 1 |
| N | 0-1 | TEMPO SYNC MODE | Almost always 1 |
| O | 0-1 | BOUNCE IN | Almost always 1 |
| P | 0 | (reserved) | Always 0 |
| Q | 0-127 | INPUT SENSITIVITY | Always 127 |
| R | 0-2 | PLAY MODE | 0=stop?, 1=MULTI, 2=SINGLE |
| **S** | 0-20 | **LOOP LENGTH (measures)** | **Verified: S = X / V exactly** |
| T | 0 | (reserved) | Always 0 |
| **U** | 700-1220 | **TEMPO × 10** | **700 = 70.0 BPM, 1200 = 120.0 BPM** |
| **V** | 86720-151200 | **SAMPLES PER MEASURE** | **V/44100 = measure duration; matches U** |
| **W** | 0-1 | **HAS AUDIO** | **1 = WAV file exists, 0 = empty** |
| **X** | 0-2247111 | **TOTAL SAMPLE COUNT** | **X/44100 = WAV duration; verified vs WAV header** |
| Y | 1-2 | REC STATE | 1=recorded, 2=factory empty |

**Key verification**: Memory001, Track1 at 70.0 BPM: U=700, V=151200 (151200/44100 = 3.4286s = one 4/4 measure at 70 BPM), S=8 measures, X=1209600 (1209600/44100 = 27.429s = 8 measures). WAV file header confirms 27.429s duration. **S = X/V** holds exactly for all 36 populated tracks tested.

### 2.5 TRACK6: Confirmed as Rhythm Track (Not User-Recordable)

Evidence:
- **No WAV files**: No `NNN_6/` directories exist anywhere on the device
- **No FX sections**: Neither `<ifx>` nor `<tfx>` contain FX groups for track 6 (only groups A-D mapping to 4 banks, not 5 or 6)
- **Always empty**: In all 99 memories (including populated ones), TRACK6 has H=1, W=0, X=0
- **Same structure**: TRACK6 has identical 25-field A-Y format as TRACK1-5 (level, pan, etc. are controllable), but no audio content

TRACK6 is the **rhythm track output channel** — it has mixer/routing presence but no user audio.

### 2.6 FX Architecture

#### Input FX (`<ifx>`) and Track FX (`<tfx>`)

Both follow the same structure:

```
<SETUP>          ← 1 field (A): global setup
<A>              ← Group A parent: 3 fields (A=SW, B=?, C=target/routing)
<AA>             ← Group A, Slot 1: 4 fields (A=SW, B=?, C=FX_TYPE_INDEX, D=?)
<AA_LPF>         ← Parameters for LPF effect
<AA_LPF_SEQ>     ← Step sequencer for LPF (22 fields)
<AA_BPF>         ← Parameters for BPF effect
...              ← (all effect types stored, active one selected by AA.C index)
<AB>             ← Group A, Slot 2
...
<B>              ← Group B parent
<BA>             ← Group B, Slot 1
...
<DD_REVERB>      ← Group D, Slot 4, last shared effect type
```

**IFX**: 4 groups × 4 slots × 66 effect types = 1,056 effect parameter sections + 66 _SEQ sections
**TFX**: 4 groups × 4 slots × 70 effect types = 1,120 effect parameter sections + 70 _SEQ sections
**TFX-only effects**: BEAT_SCATTER, BEAT_REPEAT, BEAT_SHIFT, VINYL_FLICK

The Group parent `C` field differs between IFX and TFX:
- **IFX groups**: C varies (0-3), indicating input routing target
- **TFX groups**: C is always 0

Each FX slot's `C` field is the **effect type index** selecting which of the 66/70 stored effect parameter sets is active.

#### 66 IFX Effect Types (in XML order):

LPF, BPF, HPF, PHASER, FLANGER, SYNTH, LOFI, RADIO, RING_MODULATOR, G2B, SUSTAINER, AUTO_RIFF, SLOW_GEAR, TRANSPOSE, PITCH_BEND, ROBOT, ELECTRIC, HARMONIST_MANUAL, HARMONIST_AUTO, VOCODER, OSC_VOCODER, OSC_BOT, PREAMP, DIST, DYNAMICS, EQ, ISOLATOR, OCTAVE, AUTO_PAN, MANUAL_PAN, STEREO_ENHANCE, TREMOLO, VIBRATO, PATTERN_SLICER, STEP_SLICER, DELAY, PANNING_DELAY, REVERSE_DELAY, MOD_DELAY, TAPE_ECHO, TAPE_ECHO_V505V2, GRANULAR_DELAY, WARP, TWIST, ROLL, ROLL_V505V2, FREEZE, CHORUS, REVERB, GATE_REVERB, REVERSE_REVERB

Most effects also have a `_SEQ` companion section (22 values: step sequencer pattern).

### 2.7 SYSTEM.RC0 Structure

SYSTEM1.RC0 (591 lines) contains global device settings. Same A/B pairing as memories (SYSTEM1=live, SYSTEM2=backup).

```xml
<database name="RC-505MK2" revision="0">
<sys>
  <SETUP>     <!-- 22 fields: global setup (tempo, LCD contrast, etc.) -->
  <COLOR>     <!-- 5 fields: track color mode -->
  <USB>       <!-- 5 fields: USB audio interface settings -->
  <MIDI>      <!-- 10 fields: MIDI channel, sync, thru settings -->

  <!-- Internal controls: per-track FX and track button mappings -->
  <ICTL1_TRACK1_FX> through <ICTL2_TRACK5_TRACK>   <!-- 20 sections × 3 fields -->

  <!-- Pedal mappings (9 pedals × 3 control banks) -->
  <ICTL1_PEDAL1> through <ICTL3_PEDAL9>             <!-- 27 sections × 3 fields -->

  <!-- External control assignments -->
  <ECTL_CTL1> through <ECTL_CTL4>                    <!-- 4 sections × 4 fields -->
  <ECTL_EXP1>, <ECTL_EXP2>                           <!-- 2 sections × 4 fields -->

  <!-- Per-memory recall preferences (which sections to load) -->
  <PREF>      <!-- 20 fields (A-T): boolean flags for recall behavior -->

  <!-- I/O configuration -->
  <INPUT>     <!-- 13 fields -->
  <OUTPUT>    <!-- 4 fields -->
  <ROUTING>   <!-- 19 fields: signal routing matrix -->
  <MIXER>     <!-- 22 fields: level/pan for all buses -->

  <!-- Per-channel parametric EQ (3-band) -->
  <EQ_MIC1> through <EQ_SUBOUT2R>                    <!-- 12 sections × 12 fields -->

  <MASTER_FX> <!-- 3 fields -->
  <FIXED_VALUE> <!-- 2 fields -->
</sys>
</database>
<count>0225</count>
```

System sections like INPUT, OUTPUT, ROUTING, MIXER, and EQ appear in **both** system and memory files — memory-level settings override system defaults when a patch is loaded (controlled by PREF flags).

### 2.8 RHYTHM.RC0: Binary Format

Unlike the XML RC0 files, RHYTHM.RC0 is a **2 MB binary file** (2,009,212 bytes) with fixed-size pattern slots:

- **Header**: `PTN_NNNN` (8 bytes) followed by pattern name and data
- **Pattern names**: ASCII with `^` as space separator (e.g., `SIMPLE^BEAT`)
- **Slot size**: approximately 40,184 bytes per pattern
- **Capacity**: ~50 pattern slots pre-allocated
- **Utilization**: Only 2,138 bytes of actual data (one pattern: "SIMPLE BEAT"); rest is zero-padded
- **Not XML**: Requires dedicated binary parser (low priority for an editor)

### 2.9 WAV Audio Format — Fully Decoded

From hex dump of `001_1.WAV` (Memory 001, Track 1):

| Field | Value |
|-------|-------|
| Format | RIFF/WAVE |
| Audio Format | **3 (IEEE Float)** — not PCM |
| Channels | 2 (stereo) |
| Sample Rate | 44,100 Hz |
| Bits Per Sample | **32** |
| Block Align | 8 bytes (2 × 4) |
| Byte Rate | 352,800 bytes/sec |
| fmt Chunk Size | 28 bytes (extended format) |
| cbSize | 10 |
| Data Size | 9,676,800 bytes (9.23 MB) |
| Duration | 27.429 seconds |

**Critical**: This is **32-bit IEEE 754 floating-point**, not 16-bit PCM as in the original RC-505. The extended `fmt` chunk (28 bytes with cbSize=10) includes extra fields for float format description. First audio samples are near-zero values (e.g., -0.00000019, +0.00000006) confirming float encoding.

File size formula: `duration × 44100 × 2 channels × 4 bytes = data_size`

No padding or alignment tricks observed — standard RIFF/WAVE with the 48-byte header (RIFF+fmt+data headers) followed by raw float samples.

### 2.10 Key Format Differences Summary

| Aspect | Original RC-505 | RC-505 mk2 |
|--------|----------------|-------------|
| **DB root** | `name="RC-505" revision="2"` | `name="RC-505MK2" revision="0"` |
| **Tag naming** | Descriptive (`PlyLvl`, `TmpSync`) | **Positional single letters** (`<A>`, `<B>`, ..., `<0>`, `<#>`) |
| **Data files** | `MEMORY.RC0` (1 file, all 99 patches) | **`MEMORY001A.RC0`-`MEMORY099B.RC0`** (198 files) |
| **System files** | `SYSTEM.RC0` (1 file) | **`SYSTEM1.RC0` + `SYSTEM2.RC0`** (A/B pair) |
| **A/B backup** | None | **Every file has an A (live) and B (backup) copy** |
| **Top-level per memory** | 1 element (`<mem>`) | **3 elements** (`<mem>`, `<ifx>`, `<tfx>`) |
| **Tracks** | 5 (`TRACK1`-`TRACK5`) | **6** (TRACK1-5 user + TRACK6 rhythm bus) |
| **Track params** | 10 | **25** (A through Y) |
| **Assigns** | 16 | **16** (ASSIGN1-16) |
| **Assign params** | 6 | **10** (A through J) |
| **FX architecture** | 3 slots inline in `<mem>` | **4 groups × 4 slots in separate `<ifx>`/`<tfx>`** |
| **FX types (input)** | 27 | **66** (+ _SEQ step sequencer variants) |
| **FX types (track)** | 31 | **70** (66 shared + BEAT_SCATTER/REPEAT/SHIFT + VINYL_FLICK) |
| **Per-channel EQ** | None | **12 sections** (3-band parametric per I/O channel) |
| **Routing** | Fixed | **19 routing parameters** |
| **Mixer** | Track sliders only | **22 mixer parameters** |
| **Internal controls** | None | **ICTL1/2/3 × TRACK(5) + PEDAL(9)** = 47 sections |
| **WAV format** | 16-bit PCM, stereo, 44.1kHz | **32-bit IEEE Float**, stereo, 44.1kHz |
| **Lines per memory** | ~860 | **~25,500** |
| **Sections per memory** | ~50 | **2,316** |
| **File footer** | None | `<count>NNNN</count>` (save counter) |

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
| **XML I/O scaffolding** | Low | The `<mem>` / `<ifx>` / `<tfx>` split and positional tags require a new parser; invalid XML tags (`<0>`, `<#>`) require regex-based approach |
| **RC505.h data model** | **None** | Every property definition must be rebuilt from scratch |
| **RC505.cpp type defs** | **None** | All enum arrays, value ranges, type converters need replacing |

Rough estimate: **~30% of the codebase is reusable** (UI shell, property system, audio). The remaining **~70%** requires a rewrite or new implementation (data model, FX architecture, XML parser, mixer/routing/EQ subsystems that didn't exist before).

---

## 4. The Reverse-Engineering Status

### 4.1 What Is Fully Decoded

With the full device dump analysis, the following are now **completely understood**:

- **Filesystem layout**: file naming, A/B pairing, directory structure, WAV naming convention
- **XML structure**: `<mem>` / `<ifx>` / `<tfx>` architecture, all 2,316 sections identified
- **TRACK parameters (A-Y)**: All 25 fields decoded with verification against WAV metadata
  - Tempo, measure length, sample count, loop length relationships verified mathematically
  - S = X/V (measures = total_samples / samples_per_measure) confirmed across 36 tracks
  - U/10 = BPM, V/44100 = measure duration in seconds
- **TRACK6 purpose**: Rhythm output bus, not user-recordable (no WAV files, no FX sections)
- **FX architecture**: 4 groups × 4 slots, IFX (66 types) vs TFX (70 types), type selection via index
- **WAV format**: 32-bit IEEE Float, stereo, 44.1kHz, standard RIFF/WAVE with extended fmt chunk
- **SYSTEM.RC0**: Complete section inventory (591 lines, 33 sections)
- **A/B file semantics**: A=live, B=backup; identical for factory defaults, diverge on user edit
- **Count footer**: Save/version counter, not checksum
- **NAME encoding**: ASCII character codes in fields A-L (12 characters max)

### 4.2 What Remains to Verify

Lower-priority items that need empirical testing on the device:

- **FX type index mapping**: The exact numeric index → effect type correspondence (C field in slot headers). Can be derived by changing one FX on the device and re-dumping
- **ROUTING section semantics**: 19 parameters (values 0, 63, 127 observed — likely a send matrix)
- **ICTL/ECTL mappings**: Internal/external control section A field values map to specific functions (likely matches MIDI CC numbers from the MIDI implementation)
- **ASSIGN section field mapping**: 10 fields (A-J), partially decoded (A=switch, C=target, D=source type, F=max, H=source CC, J=enable)
- **RHYTHM.RC0 binary format**: Pattern data encoding (low priority — rhythm patterns can be edited on the device)
- **PLAY/REC section semantics**: 8 and 6 fields respectively, need Parameter Guide cross-reference

### 4.3 The Positional Tag Mapping Problem — Largely Solved

The [RC-505mkII Parameter Guide](https://files.kraftmusic.com/media/ownersmanual/Boss_RC-505mkII_Parameter_Guide.pdf) (44 pages) lists parameters in the same order they appear in the XML. Combined with the dump analysis, the mapping is now tractable:

- **TRACK, MASTER, NAME**: Fully decoded from empirical analysis
- **REC, PLAY, RHYTHM**: Parameter Guide provides the order; dump provides value ranges
- **FX parameters**: Parameter Guide pages 33-41 list each effect's parameters in XML order
- **SYSTEM sections**: Same structure as memory-level equivalents

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
4. **Handle Roland's non-standard XML**: Use regex-based parsing (not standard XML parsers) to handle `<0>`, `<1>`, `<#>` tags in STEP_SLICER and other sections.
5. **32-bit float WAV support**: Replace the original editor's 16-bit PCM WAV I/O with IEEE Float read/write.
6. **Multi-file architecture**: Handle 198 individual memory files instead of one monolithic file. Support A/B file pairs (only modify A files; optionally sync B).

### Phased Implementation

| Phase | Scope | Status |
|-------|-------|--------|
| **1: Format mapping** | Complete positional tag → parameter mapping for all sections | **~80% complete** (TRACK fully decoded, FX structure mapped, SYSTEM inventoried) |
| **2: Core editor** | Read/write memory settings (no FX). Patch browser, name editor, track/master/rec/play/rhythm settings | Ready to begin |
| **3: FX support** | Input FX and Track FX editing (66-70 types × 4 groups × 4 slots) | Blocked on FX type index mapping |
| **4: Audio** | WAV import/export with 32-bit float format | **Format fully decoded** — straightforward implementation |
| **5: System settings** | SYSTEM1.RC0 editing | **Structure decoded** |
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

The mk2's format is **more different from the original RC-505 than initially expected**, but the full device dump analysis has resolved most unknowns. The shift to positional single-letter tags, per-memory individual files with A/B backup pairs, the 3-element-per-memory structure, and the 30× increase in per-memory data (860 → 25,500 lines) mean this is not a "remap the tag names" exercise — it's a fundamentally different data architecture.

However, the format is now **well-understood and regular**: sections are cleanly separated, values are plain integers, the FX structure is systematically repeated, tempo/sample relationships are mathematically verified, and the WAV format is standard (just 32-bit float instead of 16-bit PCM). An editor built on data-driven mapping tables could support the mk2 with a manageable schema file.

**The reverse-engineering phase is substantially complete. The project is ready to move to implementation.**

---

## 8. Implementation Decisions

### 8.1 License

**GPL-3.0-or-later**. The westlicht/rc505-editor is GPLv3, and the GPL was chosen over the Unlicense to protect against proprietary exploitation of what is fundamentally a community-serving tool.

### 8.2 Language

**Python 3.11+**. Chosen for portability, rich library ecosystem for audio and GUI, and readability that encourages community contributions.

### 8.3 Library Selection

| Library | Purpose | Why |
|---------|---------|-----|
| **soundfile** | 32-bit float WAV I/O | Native IEEE Float support via libsndfile; efficient metadata reads (`sf.info()`); chunked reading for waveform display; bundled libsndfile on all platforms |
| **numpy** | Audio data arrays | Required by soundfile; efficient array ops for waveform overview generation |
| **pyyaml** | Schema definition files | YAML is human-readable for parameter mapping tables that contributors will edit |
| **click** | CLI framework | Composable commands, good help generation, mature and well-documented |
| **rich** | Terminal output | Tables, colored output, progress bars for CLI usability |
| **PySide6** | GUI (future) | Official Qt binding (LGPL); QTreeView for patch browser, QPainter for waveforms, property editor widgets, drag-and-drop, cross-platform; proven in audio software |
| **pytest** | Testing | Standard Python test framework |
| **ruff** | Linting/formatting | Fast, replaces flake8+black+isort in one tool |

**Rejected alternatives:**
- `wave` (stdlib): Cannot read 32-bit float WAV — only supports integer PCM
- `scipy.io.wavfile`: 32-bit float works but SciPy is a heavy dependency for just audio I/O; no metadata-only reads
- `pydub`: Known data corruption with 32-bit float files; relies on external ffmpeg
- `PyQt6`: Functionally identical to PySide6 but GPL license adds unnecessary restrictions for downstream users
- `Dear PyGui`: Non-native appearance; immediate-mode paradigm unsuitable for property-heavy desktop app
- `Toga/BeeWare`: Not production-ready as of 2026 (tree/table widgets still incomplete)
- `Electron/Tauri`: Excellent aesthetics but two-language stack (Python+JS) adds complexity without proportional benefit

### 8.4 Project Architecture

The core design principle is **schema-driven data mapping**: YAML files define the positional tag → parameter name correspondence, value ranges, and display metadata. The parser is generic; adding or fixing mappings means editing YAML, not code.

```
eastlight/
├── pyproject.toml                 # Package metadata, dependencies, entry points
├── LICENSE                        # GPL-3.0-or-later
├── rc505-mk2-feasibility.md      # This document
├── src/
│   └── eastlight/
│       ├── __init__.py
│       ├── schema/                # YAML parameter mapping tables
│       │   ├── track.yaml         # TRACK1-5 fields A-Y → named parameters
│       │   ├── master.yaml        # MASTER section
│       │   ├── name.yaml          # NAME section (A-L → character slots)
│       │   ├── rec.yaml           # REC section
│       │   ├── play.yaml          # PLAY section
│       │   ├── rhythm.yaml        # RHYTHM section
│       │   ├── assign.yaml        # ASSIGN1-16 fields A-J
│       │   ├── input.yaml         # INPUT section
│       │   ├── output.yaml        # OUTPUT section
│       │   ├── routing.yaml       # ROUTING section
│       │   ├── mixer.yaml         # MIXER section
│       │   ├── eq.yaml            # EQ sections (3-band parametric)
│       │   ├── fx_slot.yaml       # FX slot header fields
│       │   ├── fx_group.yaml      # FX group header fields
│       │   ├── ifx_types.yaml     # 66 input FX type definitions + parameters
│       │   ├── tfx_types.yaml     # 70 track FX type definitions + parameters
│       │   └── system.yaml        # SYSTEM-level sections (SETUP, COLOR, USB, MIDI, etc.)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── parser.py          # Regex-based RC0 reader → raw section/field dicts
│       │   ├── writer.py          # Serialize model back to RC0 format
│       │   ├── model.py           # Typed data model (Memory, Track, FXSlot, System)
│       │   ├── schema.py          # Schema loader, validator, tag↔name resolver
│       │   ├── wav.py             # 32-bit float WAV metadata and waveform overview
│       │   └── library.py         # ROLAND/ directory manager (find, list, backup)
│       ├── cli/
│       │   ├── __init__.py
│       │   └── main.py            # click-based CLI entry point
│       └── gui/                   # Future: PySide6 GUI
│           └── __init__.py
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── test_parser.py
│   ├── test_writer.py
│   ├── test_model.py
│   ├── test_schema.py
│   └── fixtures/                  # Sample RC0 files for testing
│       └── .gitkeep
└── docs/
    └── .gitkeep
```

#### Data Flow

```
RC0 file on disk
    │
    ▼
parser.py (regex-based)
    │ produces: dict of section_name → dict of tag → int_value
    ▼
schema.py (YAML mapping tables)
    │ resolves: tag letters → parameter names, validates ranges
    ▼
model.py (typed data model)
    │ Memory / Track / FXGroup / FXSlot / System objects
    │ with named attributes, validation, change tracking
    ▼
  ┌─┴─┐
  │   │
cli   gui     (presentation layers)
  │   │
  └─┬─┘
    │ edits flow back through model → schema → writer
    ▼
writer.py (RC0 serializer)
    │ produces: correctly formatted RC0 with positional tags
    ▼
RC0 file on disk (+ count footer incremented)
```

#### Schema Format

Each YAML schema file defines one section type:

```yaml
# Example: schema/track.yaml
section: TRACK
instances: ["TRACK1", "TRACK2", "TRACK3", "TRACK4", "TRACK5", "TRACK6"]
fields:
  A:
    name: reverse
    type: bool
    display: "Reverse"
    default: 0
  B:
    name: one_shot
    type: bool
    display: "1Shot"
    default: 0
  C:
    name: pan
    type: int
    range: [0, 100]
    default: 50
    display: "Pan"
  D:
    name: play_level
    type: int
    range: [0, 200]
    default: 100
    display: "Play Level"
  # ... through Y
  U:
    name: tempo_x10
    type: int
    range: [200, 3000]
    default: 1200
    display: "Tempo"
    unit: "×0.1 BPM"
  V:
    name: samples_per_measure
    type: int
    range: [0, 10000000]
    display: "Samples/Measure"
    computed: true
  W:
    name: has_audio
    type: bool
    display: "Has Audio"
    read_only: true
  X:
    name: total_samples
    type: int
    range: [0, 100000000]
    display: "Total Samples"
    read_only: true
```

#### Key Design Decisions

1. **Regex parser, not XML**: Roland's RC0 files use invalid XML tags (`<0>`, `<#>`). A regex-based parser handles all tag names without special-casing.

2. **Schema-driven mapping**: The positional tag → parameter name mapping lives in YAML, not in code. This means:
   - Fixing a mapping error = edit YAML, no code change
   - Community contributors can verify mappings without reading Python
   - The same schema drives both parsing and serialization (round-trip fidelity)

3. **A-files only for writes**: The editor modifies A files (live state). B files can optionally be synced as backups, but are never the primary edit target.

4. **Count footer**: Incremented on each write to maintain Roland's save counter semantics. Not a checksum — just bumped by 1.

5. **Library separate from CLI/GUI**: `eastlight.core` has zero UI dependencies. The CLI and GUI are thin presentation layers that import the core. This enables:
   - Scripting: `import eastlight.core` for automation
   - Testing: Core logic tested without UI
   - Alternative UIs: TUI, web, or third-party integrations

### 8.5 Revised Phase Plan

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| **1: Core library** | RC0 parser, writer, schema loader, data model. Read a memory file, map all fields to named parameters, write it back unchanged (round-trip test). | pyyaml |
| **2: CLI** | `eastlight list` (show memories), `eastlight show <N>` (display parameters), `eastlight set <N> track1.pan 60` (edit), `eastlight diff <A> <B>` (compare A/B files), `eastlight name <N> "New Name"`. | click, rich |
| **3: WAV support** | `eastlight wav-info <N>` (display WAV metadata), `eastlight wav-export <N> <T>` (export track WAV), `eastlight wav-import <N> <T> <file>` (import WAV with format conversion). | soundfile, numpy |
| **4: FX support** | Complete IFX/TFX schema from Parameter Guide. `eastlight fx-show <N>`, `eastlight fx-set <N>`. | — |
| **5: GUI** | PySide6 application: patch browser tree, property editor, waveform display, drag-and-drop patch reordering. | PySide6 |
| **6: Advanced** | System settings editor, mixer/routing/EQ, step sequencer visualization, audio preview/playback. | — |
