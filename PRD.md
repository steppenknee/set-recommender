# Product Requirements Document (PRD)

## 1. Executive Summary
**Rekordbox DJ Set Recommender** is an intelligent CLI tool designed to solve set sequencing for DJs. It reads standard Pioneer Rekordbox XML collection databases, analyzes tracks using the Google Gemini API (energy, subgenre style, vocal presence, release year, vibe summary, and popularity tier), and computes mathematically and harmonically optimized track transitions using Beam Search. The resulting set list is exported back into a Rekordbox XML as a new playlist node without altering physical files or database cue points.

---

## 2. Core Problem & Value Proposition
- **The Problem**: DJs spend hours organizing track order, checking key compatibility (Circle of Fifths / Camelot), avoiding BPM jumps, managing vocal collisions, and preventing "anthem fatigue" (playing too many stone-cold classics back-to-back instead of spacing them appropriately).
- **The Solution**: An automated, intelligent pathfinding optimizer that incorporates:
  - Harmonic key shifts (smooth transitions or energetic boost shifts).
  - Absolute BPM constraints (strict 3 BPM limits).
  - Energy profile matching (presets or customized curves).
  - Track popularity & classic spacing (ensuring anthems and deep cuts are balanced unless requested as a pure classics set).
  - Vibe & sonic atmosphere summaries.
  - Vocal collision prevention.
  - Multi-artist & collaboration repetition guards.

---

## 3. Key User Personas & Use Cases
- **Club & Festival DJs**: Building high-energy peak-time sets with key modulation boosts and peak-energy climaxes.
- **Bar & Lounge DJs**: Curating multi-hour background sets with smooth harmonic blends, balanced energy waves, and deep cuts.
- **Theme & Era Set Planners**: Generating targeted mixes for specific decades (e.g., 90s house, 80s synth-pop) or mood situations described in natural language.

---

## 4. Feature Requirements

### 4.1 Metadata Enrichment & Caching
- **Subgenre Classification**: Refines broad genre tags into specific electronic styles.
- **Energy Scoring**: 1 (ambient/slow) to 10 (intense peak-time banger).
- **Vocal Type**: `full_vocal`, `vocal_hook`, or `instrumental`.
- **Release Year & Era Filtering**: Parses from XML, infers via LLM, or prompts interactively.
- **Vibe Summary**: 1-sentence description of track atmosphere, timbre, and key instrumentation.
- **Popularity Tier**: `anthem` (stone cold classic), `well_known` (club staple), `underground` (scene-recognized), or `deep_cut` (niche/rare).
- **Platform-Native Caching**: Persistent JSON cache indexed by composite SHA256 of artist and title.

### 4.2 Pathfinding & Recommendation Engine
- **Beam Search Lookahead**: Evaluates candidate sequences multiple steps ahead to find optimal pathways.
- **Classics & Anthem Distribution Guard**:
  - Penalizes back-to-back `anthem` tracks (+20.0 penalty) to prevent anthem fatigue.
  - Supports pure `classics` set mode (`--classics` or natural language prompt) where anthem clustering is welcomed.
- **Harmonic Mixing**: Camelot wheel distance metrics supporting both standard smooth blends and energetic +2/+7 boost modes.
- **Artist & Collaboration Deduplication**: Tokenizes artists across `feat.`, `vs.`, `&`, `x` with escalating set-wide repetition penalties.
- **Vocal Clashing Prevention**: Discourages consecutive full vocal tracks.

### 4.3 CLI & Export
- **Rich Terminal Output**: Displays formatted tables with Track #, Artist, Title, Year, Popularity Tier, BPM, Camelot Key, Subgenre, Rating, Vocal type, Energy, and Duration.
- **Rekordbox XML Export**: Generates compliant `<PLAYLISTS>` nodes preserving original track IDs, cues, memory loops, and beatgrids.
