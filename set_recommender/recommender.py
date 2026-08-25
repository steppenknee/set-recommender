"""
Rekordbox DJ Set Recommender - Recommendation Engine & Transition Pathfinder
Filename: set_recommender/recommender.py

This module contains the core mathematical scoring structures and pathfinding algorithms 
used to calculate optimized DJ sets. It handles:
1. Converting standard musical keys and Camelot keys to internal vector coordinates.
2. Computing transition costs based on Camelot key compatibility, BPM matching, and subgenres.
3. Factoring in track star ratings to favor highly rated tracks (rating boosting).
4. Enforcing strict same-track duplicate avoidance and consecutive/set-wide artist repetition penalties.
5. Interpolating linear target energy curves for set progressions.
6. Performing lookahead optimization via high-performance Beam Search, supporting transition overlaps.
"""

import math
import re
from typing import List, Dict, Any, Tuple, Optional, Set
from set_recommender.xml_handler import Track

def extract_artist_tokens(artist_str: str) -> Set[str]:
    """
    Extract normalized individual artist name tokens from an artist or title string.
    Splits on common collaboration delimiters: feat, ft., featuring, vs, vs., x, &, with, and, comma, slash.
    Removes extraneous punctuation, brackets, and extra spaces.
    """
    if not artist_str:
        return set()
    
    # Standardize string to lowercase
    raw = artist_str.lower()
    
    # Remove content inside brackets/parentheses that are remix or edit markers like (original mix)
    raw = re.sub(r'\b(original mix|extended mix|club mix|dub mix|remix|edit|vip|instrumental)\b', '', raw)
    
    # Split on collaboration delimiters
    parts = re.split(r'\s*(?:feat\.?|ft\.?|featuring|vs\.?|x|&|\band\b|with|/|,|\+|;)\s*', raw)
    
    tokens = set()
    for part in parts:
        cleaned = re.sub(r'[\(\)\[\]"\']', '', part).strip()
        # Filter out trivial 1-character tokens or empty strings
        if len(cleaned) >= 2:
            tokens.add(cleaned)
            
    # Also add the full normalized string if not empty
    full_clean = re.sub(r'[\(\)\[\]"\']', '', raw).strip()
    if len(full_clean) >= 2:
        tokens.add(full_clean)
        
    return tokens

def has_artist_overlap(artist1: str, artist2: str) -> bool:
    """
    Check if two artist strings share any significant artist or collaboration tokens (wildcard / substring matching).
    """
    tokens1 = extract_artist_tokens(artist1)
    tokens2 = extract_artist_tokens(artist2)
    
    if not tokens1 or not tokens2:
        return False
        
    # Check exact token match
    if tokens1.intersection(tokens2):
        return True
        
    # Check substring / wildcard overlap for artist names with length >= 4
    for t1 in tokens1:
        if len(t1) < 4:
            continue
        for t2 in tokens2:
            if len(t2) < 4:
                continue
            if t1 in t2 or t2 in t1:
                return True
                
    return False

# Mapping of standard musical key notation to standard Camelot representation
KEY_TRADITIONAL_TO_CAMELOT = {
    # Minor Keys (A)
    "g#m": (1, "A"), "abm": (1, "A"), "g# minor": (1, "A"), "ab minor": (1, "A"),
    "d#m": (2, "A"), "ebm": (2, "A"), "d# minor": (2, "A"), "eb minor": (2, "A"),
    "a#m": (3, "A"), "bbm": (3, "A"), "a# minor": (3, "A"), "bb minor": (3, "A"),
    "fm": (4, "A"), "f minor": (4, "A"),
    "cm": (5, "A"), "c minor": (5, "A"),
    "gm": (6, "A"), "g minor": (6, "A"),
    "dm": (7, "A"), "d minor": (7, "A"),
    "am": (8, "A"), "a minor": (8, "A"),
    "em": (9, "A"), "e minor": (9, "A"),
    "bm": (10, "A"), "b minor": (10, "A"),
    "f#m": (11, "A"), "gbm": (11, "A"), "f# minor": (11, "A"), "gb minor": (11, "A"),
    "c#m": (12, "A"), "dbm": (12, "A"), "c# minor": (12, "A"), "db minor": (12, "A"),
    
    # Major Keys (B)
    "b": (1, "B"), "b major": (1, "B"),
    "f#": (2, "B"), "gb": (2, "B"), "f# major": (2, "B"), "gb major": (2, "B"),
    "c#": (3, "B"), "db": (3, "B"), "c# major": (3, "B"), "db major": (3, "B"),
    "g#": (4, "B"), "ab": (4, "B"), "g# major": (4, "B"), "ab major": (4, "B"),
    "d#": (5, "B"), "eb": (5, "B"), "d# major": (5, "B"), "eb major": (5, "B"),
    "a#": (6, "B"), "bb": (6, "B"), "a# major": (6, "B"), "bb major": (6, "B"),
    "f": (7, "B"), "f major": (7, "B"),
    "c": (8, "B"), "c major": (8, "B"),
    "g": (9, "B"), "g major": (9, "B"),
    "d": (10, "B"), "d major": (10, "B"),
    "a": (11, "B"), "a major": (11, "B"),
    "e": (12, "B"), "e major": (12, "B")
}

def parse_key_to_camelot(key_str: str) -> Optional[Tuple[int, str]]:
    """
    Parse any musical key format into a standardized Camelot tuple.
    
    Compatible with Camelot directly (e.g. '8A', '11B') and traditional sharps/flats 
    (e.g., 'Am', 'G#m', 'F# major').
    
    Args:
        key_str (str): The raw key string.
        
    Returns:
        Optional[Tuple[int, str]]: Camelot numeric step and mode ('A' for minor, 'B' for major),
                                  or None if the key format could not be verified.
    """
    if not key_str:
        return None
        
    cleaned = key_str.strip().lower()
    
    # Check if the format is already standard Camelot (e.g., "8a" or "12b")
    if len(cleaned) in [2, 3] and cleaned[-1] in ["a", "b"]:
        try:
            num = int(cleaned[:-1])
            if 1 <= num <= 12:
                return (num, cleaned[-1].upper())
        except ValueError:
            pass
            
    # Lookup traditional signature maps
    return KEY_TRADITIONAL_TO_CAMELOT.get(cleaned)

def get_key_cost(key1: Optional[Tuple[int, str]], key2: Optional[Tuple[int, str]], harmonic_mode: str = "standard") -> float:
    """
    Calculate transition mismatch penalty between two Camelot keys.
    
    Applies standard harmonic mixing rules or professional energy boosting rules.
    
    Args:
        key1 (Tuple[int, str]): The source key tuple (number, mode).
        key2 (Tuple[int, str]): The destination key tuple (number, mode).
        harmonic_mode (str): Harmonic mixing mode ('standard' or 'boost').
        
    Returns:
        float: Penalty weight from 0.0 (perfect harmony) to 10.0 (clashing notes).
    """
    if not key1 or not key2:
        return 5.0  # Moderate default penalty for missing key data
        
    n1, m1 = key1
    n2, m2 = key2
    
    if harmonic_mode == "boost":
        # Professional energy boosting transitions are actively prioritized and rewarded
        if m1 == m2 and (n2 - n1) % 12 == 2:
            return 0.0  # +2 steps clockwise (Moderate boost)
        if m1 == m2 and (n2 - n1) % 12 == 7:
            return 0.0  # +7 steps clockwise (Maximum boost)
            
        # Standard flat/stable transitions are slightly penalized to push the pathfinder to boost
        if n1 == n2 and m1 == m2:
            return 2.0
        if n1 == n2 and m1 != m2:
            return 2.5
        is_fifth = (abs(n1 - n2) == 1 or abs(n1 - n2) == 11)
        if is_fifth and m1 == m2:
            return 2.5
        if is_fifth and m1 != m2:
            return 3.0
    else:
        # Standard smooth/blended harmonic mixing rules
        if n1 == n2 and m1 == m2:
            return 0.0
            
        # Relative major/minor modulation (e.g. 8A -> 8B)
        if n1 == n2 and m1 != m2:
            return 1.0
            
        diff = abs(n1 - n2)
        is_fifth = (diff == 1 or diff == 11)
        
        # Shift in fifths (one step clockwise or counter-clockwise, e.g. 8A -> 9A)
        if is_fifth and m1 == m2:
            return 1.0
            
        # Diagonal shift (e.g. 8A -> 9B)
        if is_fifth and m1 != m2:
            return 2.0
            
        # Energy boost shift (+2 steps clockwise, e.g. 8A -> 10A)
        if m1 == m2 and (n2 - n1) % 12 == 2:
            return 3.0
            
        # Semi-tone boost shift (+7 steps clockwise, e.g. 8A -> 3A)
        if m1 == m2 and (n2 - n1) % 12 == 7:
            return 4.0
            
    # Non-harmonic mismatch
    return 10.0

def get_bpm_cost(bpm1: float, bpm2: float) -> float:
    """
    Calculate transition cost between two BPM tempos.
    
    Enforces soft boundaries representing standard Pitch Fader range limits (+/- 8%).
    
    Args:
        bpm1 (float): The source track BPM.
        bpm2 (float): The destination track BPM.
        
    Returns:
        float: Mismatch penalty cost.
    """
    if bpm1 <= 0 or bpm2 <= 0:
        return 5.0
        
    bpm_diff = abs(bpm2 - bpm1)
    
    if bpm_diff <= 1.0:
        return 0.0  # Perfect/ideal tempo match
    elif bpm_diff <= 3.0:
        # Scale cost progressively up to 10.0 at exactly 3.0 BPM difference
        return (bpm_diff - 1.0) * 5.0
    else:
        return 100.0  # Mismatch exceeds the strict 3 BPM threshold

def get_genre_cost(style1: str, style2: str) -> float:
    """
    Calculate genre similarity mismatch cost between two styles.
    
    Applies a token-overlapping algorithm to assess style proximity.
    
    Args:
        style1 (str): Subgenre of the source track.
        style2 (str): Subgenre of the destination track.
        
    Returns:
        float: Mismatch penalty cost.
    """
    if not style1 or not style2:
        return 2.0
        
    s1 = style1.lower().strip()
    s2 = style2.lower().strip()
    
    if s1 == s2:
        return 0.0
        
    # Break down subgenre names into keywords
    words1 = set(s1.split())
    words2 = set(s2.split())
    
    common = words1.intersection(words2)
    # Strip common non-characterizing keywords
    common_meaningful = {w for w in common if w not in ["and", "with", "music", "style"]}
    
    if common_meaningful:
        return 1.0  # Close subgenre overlap (e.g., Deep House and Progressive House)
        
    # Cross-genre electronic mappings
    is_house1 = "house" in s1
    is_house2 = "house" in s2
    is_techno1 = "techno" in s1
    is_techno2 = "techno" in s2
    
    if (is_house1 and is_house2) or (is_techno1 and is_techno2):
        return 1.0
        
    if (is_house1 and is_techno2) or (is_techno1 and is_house2):
        return 2.0  # Transitioning House <-> Techno
        
    return 5.0  # Unrelated styles

def generate_energy_curve(progression: str, length: int) -> List[float]:
    """
    Generate target step-by-step energy values (1.0 to 10.0) based on progression presets.
    
    Args:
        progression (str): Profile name (low-to-high, high-to-low, wave, u-shape).
        length (int): Total steps in the playlist.
        
    Returns:
        List[float]: Target energy values per step.
    """
    if length <= 1:
        return [5.0] * length
        
    curve = []
    for i in range(length):
        ratio = i / (length - 1)
        
        if progression == "low-to-high":
            val = 3.0 + (9.0 - 3.0) * ratio
        elif progression == "high-to-low":
            val = 9.0 - (9.0 - 3.0) * ratio
        elif progression == "u-shape":
            if ratio < 0.5:
                sub_ratio = ratio * 2.0
                val = 8.0 - (8.0 - 4.0) * sub_ratio
            else:
                sub_ratio = (ratio - 0.5) * 2.0
                val = 4.0 + (10.0 - 4.0) * sub_ratio
        elif progression == "wave":
            val = 5.0 + 4.0 * math.sin(2.0 * math.pi * ratio)
        else:
            val = 5.0
            
        curve.append(max(1.0, min(10.0, val)))
        
    return curve

def resize_custom_progression(custom_list: List[float], target_length: int) -> List[float]:
    """
    Resize a custom energy profile to match the requested playlist step count 
    via linear interpolation.
    
    Args:
        custom_list (List[float]): User-provided energy ratings.
        target_length (int): Target length to resize to.
        
    Returns:
        List[float]: Resized list of target energy levels.
    """
    if not custom_list:
        return [5.0] * target_length
        
    if len(custom_list) == target_length:
        return custom_list
        
    if len(custom_list) == 1:
        return [custom_list[0]] * target_length
        
    resized = []
    source_len = len(custom_list)
    
    for i in range(target_length):
        src_idx = (i / (target_length - 1)) * (source_len - 1)
        idx_low = math.floor(src_idx)
        idx_high = math.ceil(src_idx)
        
        if idx_low == idx_high:
            val = custom_list[idx_low]
        else:
            weight = src_idx - idx_low
            val = custom_list[idx_low] * (1.0 - weight) + custom_list[idx_high] * weight
            
        resized.append(max(1.0, min(10.0, val)))
        
    return resized

class RecommendationPath:
    """Represents an active candidate sequence of tracks processed during Beam Search."""
    def __init__(self, tracks: List[Track] = None, cumulative_cost: float = 0.0):
        self.tracks = tracks if tracks is not None else []
        self.cumulative_cost = cumulative_cost
        self.is_done = False

    @property
    def total_duration(self) -> int:
        """Accumulated duration of all tracks inside this path (in seconds)."""
        return sum(t.duration for t in self.tracks)

    def get_actual_duration(self, overlap_seconds: int = 60) -> int:
        """
        Calculate actual playing duration accounting for track crossfade/transition overlaps.
        For N tracks, there are N-1 transitions.
        """
        if not self.tracks:
            return 0
        total = sum(t.duration for t in self.tracks)
        overlaps = len(self.tracks) - 1
        return max(0, total - (overlaps * overlap_seconds))

    def copy(self) -> "RecommendationPath":
        """Generate a copy of this candidate path."""
        path = RecommendationPath(self.tracks.copy(), self.cumulative_cost)
        path.is_done = self.is_done
        return path

def calculate_transition_cost(
    t_prev: Track, 
    t_curr: Track, 
    target_energy: float,
    w_key: float, 
    w_bpm: float, 
    w_energy: float, 
    w_genre: float,
    w_rating: float = 1.0,
    harmonic_mode: str = "standard"
) -> float:
    """
    Evaluate the total composite mismatch cost when transitioning between two tracks.
    
    Args:
        t_prev (Track): The source track.
        t_curr (Track): The destination track.
        target_energy (float): The targeted energy for this set step.
        w_key (float): Weight scalar for key.
        w_bpm (float): Weight scalar for BPM.
        w_energy (float): Weight scalar for energy.
        w_genre (float): Weight scalar for genre.
        w_rating (float, optional): Weight scalar for rating prioritization. Defaults to 1.0.
        harmonic_mode (str, optional): Harmonic mixing mode ('standard' or 'boost'). Defaults to 'standard'.
        
    Returns:
        float: Composite transition mismatch cost.
    """
    k1 = parse_key_to_camelot(t_prev.key)
    k2 = parse_key_to_camelot(t_curr.key)
    c_key = get_key_cost(k1, k2, harmonic_mode=harmonic_mode)
    
    c_bpm = get_bpm_cost(t_prev.bpm, t_curr.bpm)
    c_energy = abs(t_curr.energy - target_energy)
    c_genre = get_genre_cost(t_prev.style, t_curr.style)
    
    # Non-linear rating penalty to severely minimize 1 and 2-star tracks
    # while treating unrated (0 stars) as normal medium-tier fillers.
    if t_curr.rating == 5:
        r_penalty = 0.0
    elif t_curr.rating == 4:
        r_penalty = 1.0
    elif t_curr.rating == 3:
        r_penalty = 2.5
    elif t_curr.rating == 0:
        r_penalty = 3.0
    elif t_curr.rating == 2:
        r_penalty = 8.0  # Heavier penalty to actively discourage 2-star tracks
    elif t_curr.rating == 1:
        r_penalty = 15.0 # Severe penalty to virtually exclude 1-star tracks
    else:
        r_penalty = 3.0
        
    # Scale rating penalty dynamically based on target energy (fillers allowed in low energy; high quality required in peak energy)
    c_rating = r_penalty * (target_energy / 5.0)
    
    return (w_key * c_key) + (w_bpm * c_bpm) + (w_energy * c_energy) + (w_genre * c_genre) + (w_rating * c_rating)

def recommend_set_beam_search(
    track_pool: List[Track],
    target_tracks_count: Optional[int] = None,
    target_duration_minutes: Optional[int] = None,
    progression: str = "low-to-high",
    custom_progression: Optional[List[float]] = None,
    w_key: float = 10.0,
    w_bpm: float = 5.0,
    w_energy: float = 3.0,
    w_genre: float = 2.0,
    w_rating: float = 1.0,
    beam_width: int = 50,
    overlap_seconds: int = 60,
    harmonic_mode: str = "standard",
    allow_consecutive_anthems: bool = False
) -> List[Track]:
    """
    Execute a Beam Search pathfinding routine to find the optimal sequencing of tracks.
    
    Constructs a tree of transitions, pruning paths to retain only the top N candidates 
    at each level. Can optimize for total track count OR duration.
    
    Args:
        track_pool (List[Track]): Master pool of enriched tracks.
        target_tracks_count (int, optional): Number of tracks to target.
        target_duration_minutes (int, optional): Duration to target (in minutes).
        progression (str, optional): Energy curve preset to utilize. Defaults to "low-to-high".
        custom_progression (List[float], optional): Manual energy curve levels. Defaults to None.
        w_key (float, optional): Weight of key. Defaults to 10.0.
        w_bpm (float, optional): Weight of BPM. Defaults to 5.0.
        w_energy (float, optional): Weight of energy. Defaults to 3.0.
        w_genre (float, optional): Weight of genre. Defaults to 2.0.
        beam_width (int, optional): Search width lookahead. Defaults to 50.
        overlap_seconds (int, optional): Transition crossfade overlap in seconds. Defaults to 60.
        harmonic_mode (str, optional): Harmonic mixing mode ('standard' or 'boost'). Defaults to 'standard'.
        allow_consecutive_anthems (bool, optional): Allow back-to-back anthems for classics sets. Defaults to False.
        
    Returns:
        List[Track]: Cohesive set list of tracks.
    """
    if not track_pool:
        return []
        
    is_duration_mode = target_duration_minutes is not None
    
    # Check if this qualifies as a short mix (< 3 hours / 180 minutes) to minimize artist repetition
    is_short_mix = False
    if is_duration_mode and target_duration_minutes < 180:
        is_short_mix = True
    elif target_tracks_count is not None and target_tracks_count < 36:  # 36 tracks * ~5 mins = 180 mins
        is_short_mix = True
    
    # 1. Establish track length boundaries and target curve profiles
    if is_duration_mode:
        approx_tracks = max(3, int((target_duration_minutes * 60) / 300))
        target_len = approx_tracks
        target_secs = target_duration_minutes * 60
    else:
        target_len = min(target_tracks_count, len(track_pool))
        target_secs = 0
        
    # Fit target energy progression profile
    if custom_progression:
        target_energy_curve = resize_custom_progression(custom_progression, target_len)
    else:
        target_energy_curve = generate_energy_curve(progression, target_len)
        
    # 2. Populate starting Beam paths
    beam: List[RecommendationPath] = []
    
    for track in track_pool:
        start_energy = target_energy_curve[0]
        # Determine starting track non-linear rating penalty
        if track.rating == 5:
            r_penalty = 0.0
        elif track.rating == 4:
            r_penalty = 1.0
        elif track.rating == 3:
            r_penalty = 2.5
        elif track.rating == 0:
            r_penalty = 3.0
        elif track.rating == 2:
            r_penalty = 8.0
        elif track.rating == 1:
            r_penalty = 15.0
        else:
            r_penalty = 3.0
            
        start_cost = (w_energy * abs(track.energy - start_energy)) + (w_rating * r_penalty * (start_energy / 5.0))
        
        path = RecommendationPath([track], start_cost)
        beam.append(path)
        
    beam.sort(key=lambda p: p.cumulative_cost)
    beam = beam[:beam_width]
    
    # 3. Path Expansion Loop
    max_steps = target_len if not is_duration_mode else len(track_pool)
    current_step = 1
    
    while current_step < max_steps:
        if is_duration_mode:
            all_done = all(p.is_done for p in beam)
            if all_done:
                break
                
        # Resolve target energy for the current step
        if current_step < len(target_energy_curve):
            target_energy = target_energy_curve[current_step]
        else:
            target_energy = target_energy_curve[-1]
            
        candidates: List[RecommendationPath] = []
        
        for path in beam:
            if is_duration_mode and path.is_done:
                candidates.append(path)
                continue
                
            used_ids = {t.track_id for t in path.tracks}
            used_artists = {t.artist.strip().lower() for t in path.tracks}
            last_track = path.tracks[-1]
            
            has_extensions = False
            for next_track in track_pool:
                if next_track.track_id in used_ids:
                    continue
                    
                has_extensions = True
                cost = calculate_transition_cost(
                    last_track, 
                    next_track, 
                    target_energy,
                    w_key, 
                    w_bpm, 
                    w_energy, 
                    w_genre,
                    w_rating,
                    harmonic_mode=harmonic_mode
                )
                
                # Apply Artist Repetition Penalties with Wildcard & Collaboration Matching
                # 1. Back-to-back artist penalty (applies to ALL mixes to prevent consecutive plays by same artist or collab)
                if has_artist_overlap(next_track.artist, last_track.artist):
                    cost += 50.0  # Heavy penalty for consecutive artist / collab
                
                # 2. Set-wide artist repetition penalty (prevents recurring tracks by same artist across the set)
                artist_occurrences = sum(1 for t in path.tracks if has_artist_overlap(next_track.artist, t.artist))
                if artist_occurrences > 0:
                    # Escalating penalty for each previous appearance in the playlist
                    # 1st repeat: +25.0, 2nd repeat: +55.0, 3rd+ repeat: +90.0
                    cost += 25.0 * (artist_occurrences ** 1.3)
                    
                # Apply Consecutive Vocals Penalty to prevent lyric clashing and mental clutter in the mix
                consecutive_vocals = 0
                if next_track.vocal_type == "full_vocal":
                    consecutive_vocals = 1
                    for t in reversed(path.tracks):
                        if t.vocal_type == "full_vocal":
                            consecutive_vocals += 1
                        else:
                            break
                
                # Apply progressive penalties for consecutive vocal-heavy tracks
                if consecutive_vocals == 2:
                    cost += 8.0   # Muted penalty: discouraged, but allowed if harmonic transition is pristine
                elif consecutive_vocals >= 3:
                    cost += 35.0  # Hefty penalty: strongly forces an instrumental or vocal hook track next
                
                # Apply Anthem / Stone-Cold Classic Spacing Guard
                # Prevent anthem fatigue by spacing out legendary anthems unless specifically requested (allow_consecutive_anthems=True)
                if not allow_consecutive_anthems:
                    if next_track.popularity_tier == "anthem" and last_track.popularity_tier == "anthem":
                        cost += 20.0  # Encourage weaving deep cuts, underground, or well-known tracks between legendary anthems
                
                # Exclude hard invalid BPM transitions entirely (strict 3 BPM pitch shift boundary)
                if get_bpm_cost(last_track.bpm, next_track.bpm) >= 100.0:
                    continue
                    
                new_path = path.copy()
                new_path.tracks.append(next_track)
                new_path.cumulative_cost += cost
                
                # Handle duration window thresholds and determine if this is the final track
                is_final_track = False
                if is_duration_mode:
                    actual_dur = new_path.get_actual_duration(overlap_seconds)
                    if actual_dur >= (target_secs - 180):
                        new_path.is_done = True
                        is_final_track = True
                else:
                    if current_step == max_steps - 1:
                        is_final_track = True
                        
                # Dynamic Final Track Rule: Always end sets on high-rated tracks (4 or 5 stars)
                # Adds a heavy penalty of +40.0 if the final climax track is rated 3 stars or less.
                if is_final_track and next_track.rating <= 3:
                    new_path.cumulative_cost += 40.0
                        
                candidates.append(new_path)
                
            if is_duration_mode and not has_extensions:
                path_copy = path.copy()
                path_copy.is_done = True
                candidates.append(path_copy)
                
        if not candidates:
            break
            
        # Retain top width pathways
        candidates.sort(key=lambda p: p.cumulative_cost)
        beam = candidates[:beam_width]
        
        current_step += 1
        
        if not is_duration_mode and current_step >= target_len:
            break
            
    if not beam:
        return []
        
    # Resolve single lowest cost pathway
    beam.sort(key=lambda p: p.cumulative_cost)
    return beam[0].tracks
