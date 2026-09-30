# Product Backlog & Roadmap

This document outlines planned enhancements, feature requests, architectural improvements, and future ideas for **Rekordbox DJ Set Recommender**.

---

## 🎯 High Priority (Near-Term)

### 1. Interactive Set Editing & Replacement Prompts
- **Description**: Allow users to interactively reject specific recommended tracks or request alternative transitions directly in the CLI after set generation.
- **Goal**: Enable fine-tuning without re-running the full beam search algorithm from scratch.
- **Details**:
  - Add an interactive terminal mode (`rekordbox-set-recommender recommend --interactive`).
  - Render set preview table; prompt user: `[A]ccept, [R]eplace track #N, [E]xport`.
  - If a track is rejected, recalculate alternative candidate nodes using beam search for that slot.

### 2. Cue Point & Transition In/Out Marker Analysis
- **Description**: Leverage Rekordbox XML memory points, hot cues, and beatgrid markers to optimize transition points.
- **Goal**: Ensure key/vocal clashes are evaluated specifically across mix-in and mix-out regions rather than overall track metadata alone.
- **Details**:
  - Parse `<POSITION_MARK>` elements in Rekordbox XML (`Type="0"` for Memory Cues, `Type="1"` for Hot Cues).
  - Use cue locations to estimate intro/outro blend lengths.

### 3. Multi-Format Database Support (Serato / Traktor / Engine DJ)
- **Description**: Expand input/output support beyond Rekordbox XML to other major DJ software platforms.
- **Goal**: Make the recommender software-agnostic for multi-platform DJs.
- **Details**:
  - Add native Serato (`.crate` / database V2) and Traktor (`NML` XML format) parsers.
  - Implement a common internal track schema abstraction layer.

---

## 🔮 Medium Priority (Mid-Term)

### 4. Audio Signal DSP Feature Analysis (Local Fallback)
- **Description**: Integrate offline audio DSP feature extraction (`librosa` or `essentia`) for tracks where Gemini API metadata or track lookup fails or is unavailable.
- **Goal**: Provide offline energy scoring, key detection validation, and vocal activity detection (VAD).
- **Details**:
  - Compute RMS energy, spectral centroid, and tempo stability directly from local audio files (`.mp3`, `.wav`, `.flac`, `.aiff`).
  - Fall back to audio analysis when API key is missing or offline mode is requested (`--offline`).

### 5. Multi-Deck Transition Support (3 & 4-Deck Blending)
- **Description**: Extend pathfinding algorithms from 2-deck sequential transitions ($T_i \rightarrow T_{i+1}$) to 3/4-deck layered mix routines.
- **Goal**: Support complex layering (e.g. acapella track on Deck 3 over instrumental on Deck 1).
- **Details**:
  - Model composite state nodes representing simultaneous playing tracks.
  - Evaluate harmonic compatibility and vocal collisions across layered stems/acapellas.

### 6. Streaming Service & Metadata Provider Integration
- **Description**: Enrich metadata using Spotify, Discogs, MusicBrainz, or Beatport APIs in addition to LLM generation.
- **Goal**: Increase accuracy for niche electronic subgenres, official BPMs, and verified release years.
- **Details**:
  - Add optional fallback lookup pipelines (`--metadata-source discogs,beatport`).

---

## 💡 Low Priority / Exploratory (Long-Term)

### 7. Web UI / Desktop Companion App
- **Description**: Build a lightweight local graphical dashboard (Electron / Tauri / Streamlit) for visual set building and energy curve rendering.
- **Goal**: Provide an interactive visual canvas for DJs who prefer GUI over terminal commands.
- **Details**:
  - Render interactive energy progression curves and Camelot wheel visualizers.
  - Drag-and-drop set re-ordering with instant recalculation of transition compatibility scores.

### 8. Live Set Transition Assistant (MIDI / OSOS / DJ Link Integration)
- **Description**: Connect to live Pioneer Pro DJ Link or MIDI clocks to offer real-time next-track recommendations while performing live.
- **Goal**: Assist live improvisational sets on stage.
- **Details**:
  - Monitor active deck status via ProDJ Link / StageLinq protocols.
  - Filter cache for real-time harmonic compatibility with currently playing master deck.

---

## 📋 Technical Debt & Maintenance

- [ ] **Asynchronous API Ingestion**: Refactor `enricher.py` to use `asyncio` and `httpx` / `google-genai` async client for faster batch enrichment.
- [ ] **Performance Benchmarking**: Benchmark beam search scaling for massive Rekordbox libraries (>50,000 tracks).
- [ ] **Plugin System**: Modularize transition scoring functions into a plugin architecture for custom user-defined cost rules.
