# Feasibility: Extending westlicht/rc505-editor for RC-505 mk2 Support

## Executive Summary

Extending the [westlicht/rc505-editor](https://github.com/westlicht/rc505-editor) to support the RC-505 mk2 is **technically feasible but amounts to a near-complete rewrite of the data model layer**. The editor's architecture (C++/JUCE, property system, XML I/O) is sound and reusable, but the mk2 uses a substantially different XML schema, audio format, effect architecture, and parameter set. A realistic approach would treat the existing editor as architectural scaffolding and rebuild the data model from the mk2's actual RC0 files.

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

The editor hardcodes `revision="2"` and `name="RC-505"` in the XML root, and all ~1,742 lines of `RC505.h` define the original RC-505's exact parameter set.

---

## 2. What Changes in the mk2

### 2.1 XML Schema Differences

The mk2 belongs to a newer generation of Boss loopers (alongside RC-500 and RC-600) that use a **different XML tag naming convention**. Comparing the original RC-505 to the newer-generation format:

| Aspect | Original RC-505 | RC-505 mk2 (newer gen) |
|--------|----------------|----------------------|
| DB root | `name="RC-505" revision="2"` | Different name/revision |
| Tag style | Terse abbreviations (`Tmp`, `Lvl`, `Cs`, `Rv`, `LpSync`, `TmpSync`) | Longer descriptive names (`Tempo`, `Level`, `LoopSync`, `TempoSync`) |
| FX enable | `TrkFx` | `LoopFx` |
| Assign tags | `Src`, `SrcMod`, `Tgt`, `TgtMin`, `TgtMax` | `Source`, `SourceMode`, `Target`, `TargetMin`, `TargetMax` |
| Rec/play options | Separate `REC_OPTION`, `PLAY_OPTION` groups | Consolidated into `MASTER` |
| FX architecture | `INPUT_FX` + `TRACK_FX` + `BEAT_FX` with 3 slots each containing params for all 27-31 FX types | Restructured: 4 FX banks (A-D), 4 simultaneous slots, master FX |
| Data files | `MEMORY.RC0`, `SYSTEM.RC0` | `MEMORY1.RC0`, `MEMORY2.RC0`, `SYSTEM.RC0`, `RHYTHM.RC0` |

This means **every XML tag in the data model must be remapped**. The existing `RC505.h` property definitions cannot be reused as-is — every property name string, every XML element name, and every enum value list needs updating.

### 2.2 Audio Format

| | Original RC-505 | RC-505 mk2 |
|---|---|---|
| Bit depth | 16-bit integer | **32-bit floating point** |
| Sample rate | 44.1 kHz | 44.1 kHz |
| Channels | Stereo | Stereo |
| Special requirement | None | **512 KB padding in WAV files** |

The mk2 rejects WAV files without a proprietary 512 KB padding block. The editor's WAV import/export code (`Utils.cpp`) must be modified to write this padding, and the resampler must output 32-bit float instead of 16-bit integer.

### 2.3 Expanded Parameters

| Feature | Original RC-505 | RC-505 mk2 |
|---------|----------------|-------------|
| Input FX types | 27 | **49** |
| Track FX types | 31 | **53** |
| Simultaneous Input FX | 3 | **4** |
| Simultaneous Track FX | 3 | **4** |
| FX banks | None | **4 (A-D)** |
| Master FX | None | **2** |
| Rhythm patterns | 85 | **200** |
| Drum kits | Undocumented | **16** |
| Assigns | 16 | 16 |
| Tracks | 5 | 5 |
| Memory slots | 99 | 99 |
| XLR inputs | 1 | **2** |
| Output pairs | 1 stereo | **3 stereo** |
| Total recording time | ~3 hours | **~13 hours** |

Every new effect type needs its own parameter group with individually defined properties. The FX architecture change from 3-slot single/multi mode to 4-bank A-D is a structural redesign of the effects data model.

### 2.4 Storage Access

The original RC-505 uses a removable (glued-in) micro SD card that appears as a `BOSS_RC-505` USB volume. The mk2 has **non-removable internal storage** but still presents as USB mass storage. The volume detection code (`Library::checkVolumesForRC505()`) needs to scan for a different volume name.

---

## 3. What Can Be Reused

Despite the extensive differences, several architectural components transfer directly:

| Component | Reusability | Notes |
|-----------|-------------|-------|
| **JUCE application shell** | High | Main window, menu system, multi-document panel |
| **Property system base classes** | High | `Property`, `Group`, `BoolProperty`, `IntProperty`, `EnumProperty`, `BitSetProperty` — the type system and observer pattern are generic |
| **PropertyTreeView / PropertyView** | High | Generic UI for editing hierarchical property trees |
| **WaveformView** | High | Waveform display and drag-and-drop |
| **PatchTreeView** | High | 99-patch browser with reordering |
| **AudioEngine / LooperEngine** | Medium | Playback engine works but needs 32-bit float support |
| **LibraryTasks** | Medium | Threaded load/save with progress — needs path updates |
| **CustomLookAndFeel** | High | Pure cosmetic, fully reusable |
| **XML I/O framework** | Medium | The read/write scaffolding works, but all tag names change |
| **RC505.h data model** | **Low** | Every property definition, enum list, and XML mapping must be rewritten |
| **RC505.cpp type definitions** | **Low** | All enum-to-string arrays, value ranges, and type converters need replacing |
| **WAV import/export** | Low | Needs 32-bit float output and 512 KB padding |

Rough estimate: ~40-50% of the codebase (by line count) can be reused. The remaining 50-60% (primarily `RC505.h`, `RC505.cpp`, and effects-related code) requires a rewrite.

---

## 4. Key Technical Risks

### 4.1 Undocumented Format
The mk2's RC0 XML schema is **not publicly documented by Roland**. The commercial [rc600editor.com](https://rc600editor.com/) has reverse-engineered it but is closed-source. Development requires either:
- Access to an actual RC-505 mk2 to dump and inspect the RC0 files
- Collaboration with someone who has one
- Reverse-engineering from the mk2's MIDI SysEx parameter guide (available as a PDF from Boss)

The [RC-505mkII Parameter Guide](https://www.boss.info/global/support/by_product/rc-505mk2/owners_manuals/) (44 pages) documents all parameters and their MIDI SysEx addresses, which can serve as a reference for the expected XML structure even before seeing actual files.

### 4.2 512 KB WAV Padding
The exact format of the required padding is not publicly documented. The rc600editor handles it, but the implementation details are proprietary. This needs reverse-engineering from actual mk2 WAV files.

### 4.3 Effects Parameter Explosion
The original editor stores parameters for all possible FX types in every FX slot (27 effect types × 3 slots × multiple sections = thousands of properties per patch). The mk2 nearly doubles the effect count and adds a bank dimension. This is the most labor-intensive part of the data model work.

### 4.4 JUCE Licensing
JUCE has moved to a dual GPL/commercial license model since the editor was written. For an open-source GPLv3 project this is fine, but worth noting.

### 4.5 Stale Dependencies
The editor uses JUCE as a git submodule pinned to an old version. Modern JUCE (v7+) has API changes that may require build system updates.

---

## 5. Alternative Approaches

### 5.1 Extend the Existing Editor (Dual-Device Support)
Add a device abstraction layer so the same application supports both RC-505 and mk2. This preserves backward compatibility but doubles the data model maintenance burden.

**Effort**: High — requires abstracting the property system to be device-agnostic while maintaining two complete XML schema mappings.

### 5.2 Fork and Rewrite the Data Model
Fork the repo, gut `RC505.h`/`RC505.cpp`, and rebuild the data model for the mk2 only. Reuse the JUCE shell, property system, and UI components.

**Effort**: Medium-high — cleanest path but drops original RC-505 support.

### 5.3 Start from Scratch with a Modern Stack
Build a new editor using a web-based stack (Electron/Tauri + TypeScript) or Python (Qt/Tk). The RC0 format is just XML, so any language with XML parsing works.

**Effort**: High — but yields a more maintainable codebase and easier community contribution.

### 5.4 Extend the RC-500 Editor Instead
The [dfleury2/boss-rc500-editor](https://github.com/dfleury2/boss-rc500-editor) (C++/Qt, Nlohmann JSON, Inja templates) already uses the newer-generation XML tag naming convention. Its template-driven serialization approach may be easier to adapt to the mk2 than the westlicht editor's hardcoded property definitions.

**Effort**: Medium — the RC-500's format is closer to the mk2, and its template-based approach makes XML tag changes trivial.

---

## 6. Recommended Approach

**Option 5.2 (fork + data model rewrite) or 5.4 (extend RC-500 editor)** offer the best effort-to-value ratio.

If starting from the westlicht editor:

1. **Phase 1 — Format discovery**: Obtain RC0 file dumps from an actual mk2. Document the complete XML schema. Cross-reference with the Parameter Guide PDF.
2. **Phase 2 — Data model rewrite**: Replace `RC505.h`/`RC505.cpp` with mk2 property definitions. Consider adopting the RC-500 editor's approach of using JSON as the intermediate representation and templates for serialization, rather than hardcoded C++ property classes for every parameter.
3. **Phase 3 — Audio format**: Update WAV I/O to 32-bit float with 512 KB padding.
4. **Phase 4 — UI adaptation**: Update effect selection UIs, add FX bank controls, expand rhythm pattern lists.
5. **Phase 5 — Volume detection**: Update to detect the mk2's USB volume name.

The critical dependency is **Phase 1** — without access to actual mk2 RC0 files, the rest is speculative.

---

## 7. Existing Community Landscape

| Tool | Device | Open Source | Status |
|------|--------|------------|--------|
| [westlicht/rc505-editor](https://github.com/westlicht/rc505-editor) | RC-505 (original) | Yes (GPLv3) | Beta, unmaintained |
| [rc600editor.com](https://rc600editor.com/) | RC-505 mk2, RC-600 | No (commercial) | Active, paid |
| [dfleury2/boss-rc500-editor](https://github.com/dfleury2/boss-rc500-editor) | RC-500 | Yes | Active |
| BOSS Tone Studio | RC-505 mk2 | No (official) | Backup/restore only |

There is currently **no open-source editor for the RC-505 mk2**. This represents a real gap in the community tooling — the only option is the paid rc600editor.com or the limited official BOSS Tone Studio.

---

## 8. Conclusion

Extending rc505-editor for the mk2 is feasible — the application architecture is appropriate and roughly half the code is reusable. However, the scope is substantial: the XML schema is completely different, the audio format requires changes, the effects system has nearly doubled, and the format must be reverse-engineered from actual hardware. The project is better characterized as "building a mk2 editor using the rc505-editor as a foundation" than as "adding mk2 support." The first prerequisite is obtaining RC0 file dumps from an actual RC-505 mk2 unit.
