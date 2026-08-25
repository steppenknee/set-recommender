# Rekordbox DJ Set Recommender CLI

An intelligent command-line tool that reviews songs inside an exported Rekordbox XML database and recommends a harmonically and rhythmically optimized DJ set list based on BPM, Key, and Energy.

The app uses the **Gemini API** for lightning-fast subgenre style and 1–10 energy level classification, caches results locally to prevent duplicate costs, and solves the sequencing path via a high-performance **Beam Search** algorithm. The resulting set list is saved directly back into a standard Rekordbox-compatible XML file as a new playlist node—fully maintaining all your original cue points, active loops, memory points, beatgrids, and ratings.

---

## Key Features

- **Intelligent XML Parsing**: Reads your standard Rekordbox library and writes out structured playlist nodes without touching or corrupting your existing physical tracks, cues, or master database. Fully compatible with native Rekordbox XML schemas (supports `AverageBpm` and `Tonality` fields).
- **AI-Powered Track Lookups**: Auto-classifies track metadata (subgenre, energy 1-10, vocal presence, release year, popularity tier, and vibe summary) via Gemini's powerful structured generation.
- **Popularity Tiers & Stone-Cold Classic Spacing**: Classifies tracks into `anthem` (stone-cold classics), `well_known` (club staples), `underground`, and `deep_cut` (niche gems). Automatically spaces out legendary anthems to prevent anthem fatigue, with a `--classics` mode available for all-out greatest-hits sets.
- **Sonic Vibe Summaries**: Generates 1-sentence descriptions of each track's atmosphere, timbre, and key instrumentation.
- **Platform-Native Caching**: Saves all resolved track information and configurations securely in platform-native directories (e.g., `~/Library/Caches/rekordbox-recommender/` and `~/Library/Application Support/rekordbox-recommender/` on macOS, or XDG-compliant standard directories on Linux) to guarantee instantaneous subsequent runs and protect against redundant API calls. Includes seamless self-executing legacy migration.
- **Natural Language Situations (`--situation` / `-s`)**: Describe your gig in plain English (e.g., `"6 hours set in a mexican bar from 5pm to 11pm"` or `"high energy peak time party"`). Gemini will dynamically parse the target duration/track counts and synthesize customized transition weights and energy progression curves on the fly!
- **Star Ratings Display & Boosting**: Automatically reads track ratings from Rekordbox (1 to 5 stars), displays them as stars (`⭐⭐⭐⭐`) in the terminal table, and applies a rating priority boost (`--weight-rating`) during pathfinding to favor your favorite tracks.
- **Blended Playtime Estimation (`--transition-overlap`)**: Factor in transition overlaps (crossfade blend time in seconds, default `60`s) to calculate an accurate **Estimated Continuous Playtime** rather than a simple raw mathematical sum of track lengths.
- **Strict Duplicate & Artist Repetition Guards (with Wildcard / Collab Matching)**: 
  * Duplicates of the same track are strictly prevented from appearing twice.
  * Automatically parses and identifies collaboration markers (`feat.`, `ft.`, `vs.`, `x`, `&`, `with`) to match artists across solo and featured tracks.
  * Back-to-back consecutive plays of the same artist/collaborator are heavily penalized (`+50.0`).
  * Enforces an escalating set-wide repetition penalty across the mix to maximize artist variety and prevent recurring track clusters.
- **Dynamic Energy Progressions**: Choose standard preset paths (`low-to-high`, `high-to-low`, `wave`, `u-shape`) or pass an exact custom energy curve list (e.g., `--custom-progression "3,4,6,5,8,9,7"`).
- **Harmonic Mixing**: Fully supports standard **Camelot Keys** (e.g., `8A`, `11B`) and musical keys (e.g., `Am`, `G#m`), mapping transitions on the Circle of Fifths.
- **Beam Search Path-Finder**: Employs a state-of-the-art beam search transition optimizer to look multiple steps ahead and minimize transitions clashing in key, BPM, and genre.

---

## Installation & Setup

1. **Clone and Navigate**:
   ```bash
   cd set-recommender
   ```

2. **Install Dependencies**:
   Ensure you have Python 3.10+ installed. Install the package and its requirements:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Gemini API Key**:
   Provide your Gemini API key via your environment variables:
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```
   *Note: If not provided, the CLI will prompt you to enter the key on its first run and save it to your native application config directory.*

---

## Usage Guide

### 1. Enrich Track Metadata (Optional)
To query Gemini and pre-populate your cache file with genre styles and energy ratings for your library:
```bash
rekordbox-set-recommender enrich my_collection.xml
```

### 2. Generate a Recommended DJ Set List
To create an optimized playlist, run `recommend`. This will instantly evaluate transitions and output a new Rekordbox-ready XML file:

```bash
rekordbox-set-recommender recommend \
    my_collection.xml \
    my_collection_with_set.xml \
    --tracks 15 \
    --progression low-to-high \
    --playlist-name "Sunset Warmup Set"
```

### 3. Natural Language Set Generation & Decade/Era Filtering
Describe the situation (including decades or eras) to automatically set duration, transition weights, energy curve profiles, and decade filters:
```bash
rekordbox-set-recommender recommend \
    my_collection.xml \
    my_collection_with_set.xml \
    --situation "90s house party set" \
    --harmonic-mode boost
```
You can also explicitly filter by decade or exact release years:
```bash
rekordbox-set-recommender recommend \
    my_collection.xml \
    my_collection_with_set.xml \
    --decade 90s \
    --tracks 20
```

### 4. Classics Sets vs. Balanced Anthems
By default, the pathfinder spaces out legendary anthems to prevent anthem fatigue and weave underground tracks/deep cuts in between. For a dedicated all-out greatest-hits mix, use `--classics`:
```bash
rekordbox-set-recommender recommend \
    my_collection.xml \
    my_collection_with_set.xml \
    --classics \
    --situation "Ibiza all-time dance anthems"
```

---

## Technical Specifications
For full technical specifications on the algorithm mismatch cost scoring formulas, Camelot key mapping matrices, and JSON cache schemas, see [`spec.md`](spec.md).
