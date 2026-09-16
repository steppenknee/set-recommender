# Rekordbox DJ Set Recommender - Technical Specification

This document provides a formal technical specification for the Rekordbox DJ Set Recommender CLI.

---

## 1. CLI Commands & Options

The application is built using Python's `typer` library and structured into two primary command contexts.

### Command `enrich`
Enriches the tracks in a Rekordbox XML with subgenre and energy data, saving the results in a local cache.

```bash
rekordbox-set-recommender enrich [OPTIONS] INPUT_XML
```

* **Arguments**:
  * `INPUT_XML` (Path, Required): Path to the source Rekordbox XML file.
* **Options**:
  * `--api-key` (String, Optional): Gemini API Key. Overrides the `GEMINI_API_KEY` environment variable and local config file.
  * `--batch-size` (Int, Default `20`): Number of tracks to process per API payload batch to avoid rate limits.
  * `--force` (Bool, Default `False`): Force re-fetching from Gemini even if a track is already cached.

### Command `recommend`
Reviews the tracks, calculates the optimal set list, and generates a new Rekordbox XML file containing the recommended playlist.

```bash
rekordbox-set-recommender recommend [OPTIONS] INPUT_XML OUTPUT_XML
```

* **Arguments**:
  * `INPUT_XML` (Path, Required): Path to the source Rekordbox XML file.
  * `OUTPUT_XML` (Path, Required): Target path to write the new Rekordbox XML file.
* **Options**:
  * `--tracks` (Int, Optional): Exact number of tracks for the recommended set. Mutually exclusive with `--duration`.
  * `--duration` (Int, Optional): Target duration of the set in minutes. Mutually exclusive with `--tracks`.
  * `--progression` (String, Default `low-to-high`): Preset progression: `low-to-high`, `high-to-low`, `wave`, `u-shape`.
  * `--custom-progression` (String, Optional): Comma-separated list of target energy numbers (1-10), e.g., `"2,4,4,6,8,8,6,7"`. Overrides `--progression`.
  * `--playlist-name` (String, Default `"Recommended Set"`): The name of the playlist node inserted into the XML.
  * `--weight-key` (Float, Default `10.0`): Transition mismatch penalty weight for harmonic key compatibility.
  * `--weight-bpm` (Float, Default `5.0`): Transition mismatch penalty weight for BPM differences.
  * `--weight-energy` (Float, Default `3.0`): Mismatch penalty weight for deviating from the target energy profile.
  * `--weight-genre` (Float, Default `2.0`): Transition mismatch penalty weight for subgenre clashes.
  * `--weight-rating` (Float, Default `2.0`): Mismatch penalty weight for lower-rated tracks (biases toward 4 and 5-star tracks).
  * `--beam-width` (Int, Default `50`): Number of parallel paths maintained during beam search optimization.
  * `--harmonic-mode` (String, Default `standard`): Harmonic mixing mode (`standard` for smooth blends, `boost` for energetic Camelot shifts).
  * `--classics` (Bool, Default `False`): Allow back-to-back anthems / stone-cold classics (ideal for greatest-hits and classics sets).
  * `--decade` (String, Optional): Filter candidate tracks by decade (`70s`, `80s`, `90s`, `2000s`, `2010s`, `2020s`).
  * `--year-min` (Int, Optional): Filter candidate tracks released on or after this year.
  * `--year-max` (Int, Optional): Filter candidate tracks released on or before this year.
  * `--situation` / `-s` (String, Optional): A human-like mood/situation description (e.g., `"early evening bar"`, `"90s party"`) to dynamically parse duration/track counts, era/decade constraints (`min_year`/`max_year`), classics mode, and override search weights/progressions using Gemini.
  * `--api-key` (String, Optional): Gemini API Key. Overrides environment variables and native config.

---

## 2. Input/Output Data Schema & Caching

The application conforms strictly to standard OS-specific directories to keep the user's home directory pristine.

### 2.1 Configuration File
Stores configuration parameters.
* **macOS Path**: `~/Library/Application Support/rekordbox-recommender/config.json`
* **Linux/Other Path**: `~/.config/rekordbox-recommender/config.json`

```json
{
  "GEMINI_API_KEY": "AIzaSy..."
}
```

### 2.2 Cache Database File
Caches enriched track styles, energy levels, vocal presence types, popularity tiers, vibe summaries, and release years. Tracks are indexed based on a composite SHA256 key of artist and title.
* **macOS Path**: `~/Library/Caches/rekordbox-recommender/cache.json`
* **Linux/Other Path**: `~/.cache/rekordbox-recommender/cache.json`

```json
{
  "f107c1b48b7d923058869c3a3821033b06cf72a5a542b8e3a2ffcd93e9619623": {
    "artist": "Rufus Du Sol",
    "title": "On My Knees",
    "style": "Melodic Techno",
    "energy": 7,
    "vocal_type": "full_vocal",
    "popularity_tier": "anthem",
    "summary": "Hypnotic rolling bassline layered with emotive male vocals and driving peak-time synthesizers.",
    "year": 2021
  }
}
```
*Note: A safe, self-executing legacy migration automatically moves legacy configuration and cache files from `~/.rekordbox-recommender` on startup if present, preserving existing track data.*

### 2.3 Gemini API Interaction Schema
The payload sent to the Gemini API (`gemini-2.5-flash`) utilizes JSON Schema enforcement to guarantee structured output:

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "artist": {"type": "string"},
      "title": {"type": "string"},
      "style": {
        "type": "string",
        "description": "Specific subgenre/style (e.g., Deep House, Peak Time Techno, Progressive House, Indietronica)"
      },
      "energy": {
        "type": "integer",
        "minimum": 1,
        "maximum": 10,
        "description": "Perceived intensity/energy level of the track from 1 (very chill) to 10 (intense peak time)"
      },
      "vocal_type": {
        "type": "string",
        "enum": ["full_vocal", "vocal_hook", "instrumental"],
        "description": "Vocal presence: 'full_vocal' (continuous vocals/lyrics), 'vocal_hook' (minimal hooks/chants/samples), or 'instrumental' (pure instrumental)."
      },
      "year": {
        "type": "integer",
        "description": "Original release year of the track (e.g. 1995, 2024)."
      },
      "popularity_tier": {
        "type": "string",
        "enum": ["anthem", "well_known", "underground", "deep_cut"],
        "description": "Cultural familiarity level: 'anthem' (stone-cold classic), 'well_known' (club staple), 'underground' (scene track), or 'deep_cut' (niche crate-digger B-side)."
      },
      "summary": {
        "type": "string",
        "description": "A concise 1-sentence summary of the track's sonic vibe, atmosphere, timbre, and key instrumentation."
      }
    },
    "required": ["artist", "title", "style", "energy", "vocal_type", "popularity_tier", "summary"]
  }
}
```

---

## 3. Key Conversion Matrix & Distance Rules

To calculate harmonic compatibility, all musical keys are mapped to their corresponding integer representation on the **Camelot Wheel** (1 to 12) and their mode (A = Minor, B = Major). Supports both sharps (`#`) and flats (`b`), with automatic fallback handling between `Tonality` and `Key` XML fields.

### Musical Key Map Table

| traditional key | camelot key | traditional key | camelot key |
| :--- | :---: | :--- | :---: |
| **Abm / G#m** | 1A | **B** | 1B |
| **Ebm / D#m** | 2A | **F# / Gb** | 2B |
| **Bbm / A#m** | 3A | **Db / C#** | 3B |
| **Fm** | 4A | **Ab / G#** | 4B |
| **Cm** | 5A | **Eb / D#** | 5B |
| **Gm** | 6A | **Bb / A#** | 6B |
| **Dm** | 7A | **F** | 7B |
| **Am** | 8A | **C** | 8B |
| **Em** | 9A | **G** | 9B |
| **Bm** | 10A | **D** | 10B |
| **F#m / Gbm** | 11A | **A** | 11B |
| **C#m / Dbm** | 12A | **E** | 12B |

### Mismatch Penalty Rules ($C_{\text{key}}$)
Let Key 1 be $K_1 = (N_1, M_1)$ and Key 2 be $K_2 = (N_2, M_2)$, where $N \in [1, 12]$ and $M \in \{A, B\}$.

The system operates in one of two modes depending on `--harmonic-mode`:

1. **Standard Mode** (Default): Prioritizes smooth, blended harmonic transitions.
   - **Perfect Match**: $N_1 = N_2$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 0.0$
   - **Fifth Shift (1 step clockwise/counterclockwise)**: $|N_1 - N_2| \in \{1, 11\}$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 1.0$
   - **Relative Mode Change**: $N_1 = N_2$ and $M_1 \neq M_2 \rightarrow C_{\text{key}} = 1.0$
   - **Diagonal Shift (1 step fifth + mode change)**: $|N_1 - N_2| \in \{1, 11\}$ and $M_1 \neq M_2 \rightarrow C_{\text{key}} = 2.0$
   - **Energy Boost (+2 steps)**: $(N_2 - N_1) \pmod{12} = 2$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 3.0$
   - **Semi-tone Boost (+7 steps)**: $(N_2 - N_1) \pmod{12} = 7$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 4.0$
   - **Unharmonic Match**: All other combinations $\rightarrow C_{\text{key}} = 10.0$

2. **Boost Mode**: Actively favors and rewards energetic key modulations to drive set energy upward.
   - **Energy Boost (+2 steps)**: $(N_2 - N_1) \pmod{12} = 2$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 0.0$
   - **Semi-tone Boost (+7 steps)**: $(N_2 - N_1) \pmod{12} = 7$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 0.0$
   - **Perfect Match**: $N_1 = N_2$ and $M_1 = M_2 \rightarrow C_{\text{key}} = 2.0$ *(Slightly penalized to encourage boosting)*
   - **Relative Mode Change / Fifth Shift**: $C_{\text{key}} = 2.5$
   - **Diagonal Shift**: $C_{\text{key}} = 3.0$
   - **Unharmonic Match**: All other combinations $\rightarrow C_{\text{key}} = 10.0$

---

## 4. Pathfinding Strategy: Beam Search Specification

The recommended track list of length $N$ is generated from a collection pool $P$ containing $M$ tracks using a **Beam Search** algorithm.

### Dynamic Track Rounding & Backup Buffer
To ensure DJs always have spare tracks "just in case", the requested target track count is dynamically adjusted prior to pathfinding:
1. **Duration Conversion**: If a target duration $D$ is requested, it is converted to a base track count: $T_{\text{base}} = \max\left(3, \left\lfloor \frac{D \times 60}{240} \right\rfloor\right)$ (assuming an average of 4 playing minutes per track including transition overlaps).
2. **Nearest-5 Rounding**: The track count is rounded up to the nearest multiple of 5: $N_{\text{rounded}} = \left\lceil \frac{T_{\text{base}}}{5} \right\rceil \times 5$.
3. **Buffer Addition**: If the rounding did not add any tracks (meaning $T_{\text{base}}$ was already a multiple of 5), an extra 5 tracks are added to guarantee a buffer of backup selections: $N = N_{\text{rounded}} + 5$. If it did add tracks, $N = N_{\text{rounded}}$.

Let a partial path of length $k$ be represented as $S = [t_1, t_2, \dots, t_k]$ where $t_i \in P$. The cumulative cost of a path $S$ is:
$$\text{Cost}(S) = \sum_{i=1}^{k-1} \text{TransitionCost}(t_i, t_{i+1}, i+1)$$

### TransitionCost Function
$$\text{TransitionCost}(T_{\text{prev}}, T_{\text{curr}}, \text{step}) = w_{\text{key}} \cdot C_{\text{key}} + w_{\text{BPM}} \cdot C_{\text{BPM}} + w_{\text{energy}} \cdot | \text{Energy}(T_{\text{curr}}) - E^*_{\text{step}} | + w_{\text{genre}} \cdot C_{\text{genre}} + w_{\text{rating}} \cdot C_{\text{rating}}$$

- $C_{\text{BPM}} = \begin{cases} 
      0.0 & \text{if } \text{Diff} \le 1.0\text{ BPM} \\
      (\text{Diff} - 1.0) \cdot 5.0 & \text{if } 1.0 < \text{Diff} \le 3.0\text{ BPM} \\
      100.0 & \text{if } \text{Diff} > 3.0\text{ BPM} 
   \end{cases}$
  with $\text{Diff} = |\text{BPM}_{\text{curr}} - \text{BPM}_{\text{prev}}|$. Enforces a strict absolute maximum tempo fader adjustment of 3 BPM.
- $C_{\text{genre}} = \begin{cases}
      0.0 & \text{if subgenres are identical} \\
      1.0 & \text{if subgenres are compatible} \\
      10.0 & \text{otherwise}
   \end{cases}$
- $C_{\text{rating}} = R_{\text{penalty}} \times \frac{\text{TargetEnergy}}{5.0}$ where:
  - $R_{\text{penalty}} = 0.0$ for 5 stars, $1.0$ for 4 stars, $2.5$ for 3 stars, $3.0$ for unrated (0 stars), $8.0$ for 2-star tracks (heavy penalty), and $15.0$ for 1-star tracks (severe penalty).
  This non-linear rating penalty structure severely discourages the selection of poor-quality 1 and 2-star filler tracks, while treating unrated songs as standard neutral options, all scaled dynamically by the current target energy level.

### Blended Playtime & Duration Threshold
When optimizing for a target duration, the raw mathematical sum of track lengths is adjusted by a transition overlap factor (in seconds) to calculate the actual playtime:
$$\text{ActualPlaytime}(S) = \left( \sum_{i=1}^{k} \text{Duration}(T_i) \right) - (k - 1) \times \text{Overlap}$$

A candidate path is flagged as complete once `ActualPlaytime(S) >= TargetSeconds - 180` (within a 3-minute window of the target duration).

### Constraints & Special Penalties
To maintain optimal set variety and set structure, the pathfinder enforces strict constraints during node expansion:
1. **Track Duplicates**: Exact duplicate track IDs are completely skipped (`continue`).
2. **Wildcard & Collaboration Token Matching**: Artist names are parsed and split on collaboration markers (e.g. `feat.`, `ft.`, `featuring`, `vs.`, `x`, `&`, `and`, `with`, `/`, `,`) and normalized to match individual artists across solo and featured releases.
3. **Back-to-Back Consecutive Play**: Transitioning between two tracks sharing an artist or collaboration token adds an immediate heavy penalty of `+50.0` to the transition cost across all set lengths.
4. **Set-Wide Artist Repetition Guard**: For each previous occurrence of any shared artist or collaborator in the active path, an escalating penalty is applied: $\text{Penalty}_{\text{artist}} = 25.0 \times (\text{Occurrences})^{1.3}$ (e.g., $+25.0$ on first repeat, $+55.0$ on second repeat, $+90.0$ on third repeat), ensuring wide artist diversity across the entire set.
5. **Dynamic Climax (Final Track)**: The final track of the set is critical. If the last climax track has a rating of 3 stars or less, a severe penalty of `+40.0` is added to its cumulative cost to ensure the set ends on a strong favorite.
6. **Consecutive Vocals Guard**: To prevent lyric clashes and mental clutter in the mix, consecutive `full_vocal` tracks are penalized:
   - 2 `full_vocal` tracks consecutively: adds `+8.0` penalty (discouraged, but allowed if harmonic matching is pristine).
   - 3 or more `full_vocal` tracks consecutively: adds `+35.0` penalty (heavily penalized, strongly forcing an instrumental or vocal hook next).
7. **Anthem & Stone-Cold Classic Spacing Guard**: To prevent anthem fatigue, playing back-to-back `anthem` tier tracks adds a `+20.0` transition penalty in standard mode, encouraging the beam search to weave deep cuts, underground tracks, or club hits between legendary classics. This penalty is completely disabled when `--classics` is passed or when an all-time classics situation is requested.

### Beam Search Algorithm Iteration Loop
1. Initialize the beam $B_0 = \{ [t] \mid t \in P \}$ representing all tracks as potential starting points. The starting cost of a path $[t]$ is:
   $$\text{Cost}([t]) = w_{\text{energy}} \cdot |\text{Energy}(t) - E^*_1| + w_{\text{rating}} \cdot (5.0 - \text{Stars}(t)) \cdot \frac{E^*_1}{5.0}$$
2. For each step $k$ from $2$ to $N$:
   - Let $B_{\text{candidates}} = \emptyset$
   - For each path $S \in B_{k-1}$:
     - If in duration mode and $S$ is flagged as complete, add $S$ directly to $B_{\text{candidates}}$ and continue.
     - For each track $t \in P$ not currently in $S$:
       - Calculate $\text{Cost}(S + [t]) = \text{Cost}(S) + \text{TransitionCost}(S[-1], t, k)$ with any applicable artist penalties.
       - Add the candidate path $S + [t]$ to $B_{\text{candidates}}$
   - Sort $B_{\text{candidates}}$ in ascending order of their cumulative cost.
   - Retain only the top $W$ (beam-width) candidates in $B_k$.
3. When $k = N$ (or all paths in $B$ are complete in duration mode), output the single path in $B$ with the lowest cost.
