"""
Rekordbox DJ Set Recommender - Metadata Enrichment Engine
Filename: set_recommender/enricher.py

This module batch-enriches parsed Track metadata by querying the Gemini API 
via the official google-genai Python SDK. To optimize response speed and eliminate 
unnecessary API costs, all fetched metadata values (electronic subgenres and energy 
levels) are cached locally in cache.json.
"""

import hashlib
import warnings
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from set_recommender.xml_handler import Track
from set_recommender.config import load_cache, save_cache, get_api_key

# Suppress the Google GenAI SDK Automatic Function Calling deprecation warning
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", message=".*Automatic Function Calling.*")

class TrackEnrichment(BaseModel):
    """
    Pydantic schema representing individual track metadata returned by the LLM.
    Used for structured Gemini response matching.
    """
    artist: str = Field(description="Exact artist name provided in the input.")
    title: str = Field(description="Exact track title/name provided in the input.")
    style: str = Field(description="The precise electronic music subgenre or style (e.g. Deep House, Melodic Techno, Progressive House, Tech House, Trance, Drum & Bass, Ambient).")
    energy: int = Field(description="The perceived energy level of the track on a scale from 1 (chill/ambient/warmup) to 10 (highly energetic peak-time banger).")
    vocal_type: Literal["full_vocal", "vocal_hook", "instrumental"] = Field(
        description="The vocal presence type of the track. "
                    "'full_vocal' means lyric-heavy, song-like vocals throughout. "
                    "'vocal_hook' means minimal vocal snippets, hooks, chants, or repeated samples. "
                    "'instrumental' means pure instrumental with no human vocals."
    )
    year: Optional[int] = Field(None, description="The release year of the track/song (e.g. 1995, 2004, 2023). If completely unknown, return null.")
    popularity_tier: Literal["anthem", "well_known", "underground", "deep_cut"] = Field(
        description="The cultural popularity and familiarity level of the track: "
                    "'anthem' = stone-cold classic, legendary peak-time anthem universally recognized across dance music history; "
                    "'well_known' = popular club staple or hit in its respective genre; "
                    "'underground' = respected scene track recognized by genre fans and DJs; "
                    "'deep_cut' = niche, obscure, B-side, or rare crate-digger track."
    )
    summary: str = Field(description="A concise 1-sentence summary of the track's sonic vibe, atmosphere, timbre, and key instrumentation (e.g., 'Hypnotic rolling bassline layered with melancholic synths and punchy 909 kicks').")

class BatchEnrichmentResponse(BaseModel):
    """
    Pydantic wrapper class containing a batch of TrackEnrichments.
    Forces Gemini API to output structured JSON matching this schema exactly.
    """
    tracks: List[TrackEnrichment]

def sanitize_metadata_string(s: str) -> str:
    """
    Sanitize raw track metadata to prevent escaping and JSON repetition bugs in Gemini.
    """
    if not s:
        return ""
    # Strip any leading/trailing whitespace
    s = s.strip()
    # Replace backslashes with forward slashes to avoid escape-state confusion
    s = s.replace("\\", "/")
    # Remove double quotes and control characters to prevent JSON formatting breaking
    s = s.replace('"', "").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return s

def get_track_hash(artist: str, title: str) -> str:
    """
    Generate a deterministic SHA256 hash identifying a unique track.
    Combines normalized lowercase artist and title strings.
    """
    raw_key = f"{artist.strip().lower()}|{title.strip().lower()}".encode("utf-8")
    return hashlib.sha256(raw_key).hexdigest()

def enrich_batch_with_retry(
    client: genai.Client,
    batch: List[Track],
    cache: Dict[str, Any]
) -> None:
    """
    Process a batch of tracks with Gemini structured outputs.
    If the call fails or JSON is invalid, recursively split the batch into halves and retry,
    down to a single track. If a single track fails, fall back to safe default.
    """
    if not batch:
        return

    # Format unstructured track metadata list as a clear, sequential prompt
    prompt_lines = [
        "Review the following DJ music tracks and classify their electronic subgenre/style, 1-10 energy level, "
        "vocal presence type ('full_vocal', 'vocal_hook', or 'instrumental'), release year (4-digit integer), "
        "popularity tier ('anthem', 'well_known', 'underground', or 'deep_cut'), and a 1-sentence vibe/timbre summary:\n"
    ]
    for idx, track in enumerate(batch):
        clean_artist = sanitize_metadata_string(track.artist)
        clean_title = sanitize_metadata_string(track.title)
        clean_genre = sanitize_metadata_string(track.genre)
        year_hint = f" (Year: {track.year})" if track.year and track.year > 0 else ""
        genre_hint = f" (Genre: {clean_genre})" if clean_genre else ""
        prompt_lines.append(f"{idx+1}. Artist: {clean_artist} | Title: {clean_title}{genre_hint}{year_hint}")
    
    prompt_content = "\n".join(prompt_lines)
    
    try:
        # Query Gemini using standard Pydantic schema enforcement (application/json)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_content,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a precise world-class music database classifier and dance music historian. "
                    "Analyze the list of tracks and return a valid JSON object matching the schema exactly. "
                    "Determine original release year, accurately categorize anthems / classics vs well_known vs underground vs deep cuts, "
                    "and provide crisp 1-sentence vibe summaries. Keep all string values clean and properly formatted."
                ),
                response_mime_type="application/json",
                response_schema=BatchEnrichmentResponse,
                temperature=0.2,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),
        )
        
        # Unpack and validate structured JSON
        validated_response = BatchEnrichmentResponse.model_validate_json(response.text)
        
        # Match schema results back to tracks in the current batch
        for idx, enriched in enumerate(validated_response.tracks):
            if idx < len(batch):
                target_track = batch[idx]
                target_track.style = enriched.style
                target_track.energy = enriched.energy
                target_track.vocal_type = enriched.vocal_type
                target_track.popularity_tier = enriched.popularity_tier
                target_track.summary = enriched.summary
                if (not target_track.year or target_track.year == 0) and enriched.year:
                    target_track.year = enriched.year
                
                # Save inside the local cache database
                track_hash = get_track_hash(target_track.artist, target_track.title)
                cache[track_hash] = {
                    "artist": target_track.artist,
                    "title": target_track.title,
                    "style": enriched.style,
                    "energy": enriched.energy,
                    "vocal_type": enriched.vocal_type,
                    "popularity_tier": enriched.popularity_tier,
                    "summary": enriched.summary,
                    "year": target_track.year
                }
    except Exception as e:
        # If the batch has more than 1 track, split in half and retry recursively
        if len(batch) > 1:
            mid = len(batch) // 2
            left_batch = batch[:mid]
            right_batch = batch[mid:]
            enrich_batch_with_retry(client, left_batch, cache)
            enrich_batch_with_retry(client, right_batch, cache)
        else:
            # Single track failed; apply fallback and log warning
            failed_track = batch[0]
            failed_track.style = failed_track.genre if failed_track.genre else "Electronic"
            failed_track.energy = 5  # Safe neutral default
            failed_track.vocal_type = "instrumental"
            failed_track.popularity_tier = "underground"
            failed_track.summary = f"{failed_track.style} track"
            track_hash = get_track_hash(failed_track.artist, failed_track.title)
            cache[track_hash] = {
                "artist": failed_track.artist,
                "title": failed_track.title,
                "style": failed_track.style,
                "energy": failed_track.energy,
                "vocal_type": failed_track.vocal_type,
                "popularity_tier": failed_track.popularity_tier,
                "summary": failed_track.summary,
                "year": failed_track.year
            }
            print(f"\n[Warning] API enrichment failed for individual track '{failed_track.artist} - {failed_track.title}': {e}. Applying fallback parameters.")

def enrich_tracks(
    tracks: List[Track], 
    api_key: str, 
    batch_size: int = 20, 
    force: bool = False
) -> List[Track]:
    """
    Enrich a list of Track objects with electronic music subgenre styles and 1-10 energy values.
    
    Coordinates cache checks, local database loading, and structured calls to 
    the Gemini API (model: gemini-2.5-flash) to retrieve metadata in batches.
    
    Args:
        tracks (List[Track]): List of parsed Track objects.
        api_key (str): Authorized Gemini API key.
        batch_size (int, optional): Number of tracks to process per API query to avoid rate limits. Defaults to 20.
        force (bool, optional): Force re-fetching from Gemini even if already cached. Defaults to False.
        
    Returns:
        List[Track]: Fully enriched list of tracks.
    """
    cache = load_cache()
    
    # 1. Identify which tracks need to query the Gemini API
    tracks_to_enrich: List[Track] = []
    
    for track in tracks:
        track_hash = get_track_hash(track.artist, track.title)
        
        if not force and track_hash in cache:
            # Rehydrate from cached database record
            cached_data = cache[track_hash]
            track.style = cached_data.get("style", "Unknown")
            track.energy = cached_data.get("energy", 5)
            track.vocal_type = cached_data.get("vocal_type", "instrumental")
            track.popularity_tier = cached_data.get("popularity_tier", "underground")
            track.summary = cached_data.get("summary", "")
            cached_year = cached_data.get("year", 0)
            if (not track.year or track.year == 0) and cached_year:
                track.year = cached_year
        else:
            tracks_to_enrich.append(track)
            
    # Process un-cached tracks if any
    if tracks_to_enrich:
        # 2. Instantiate Gemini Client
        client = genai.Client(api_key=api_key)
        
        # 3. Process batches of tracks using a beautiful terminal progress bar
        total_tracks = len(tracks_to_enrich)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task(f"Enriching {total_tracks} tracks via Gemini...", total=total_tracks)
            
            for i in range(0, total_tracks, batch_size):
                batch = tracks_to_enrich[i:i+batch_size]
                enrich_batch_with_retry(client, batch, cache)
                progress.update(task, advance=len(batch))
                
        # Write the updated cache database back to disk
        save_cache(cache)
    
    # 4. Prompt user to provide release year for any tracks where year is still unknown (0)
    missing_year_tracks = [t for t in tracks if not t.year or t.year == 0]
    if missing_year_tracks:
        print(f"\n[Info] {len(missing_year_tracks)} track(s) have no release year metadata.")
        for t in missing_year_tracks:
            try:
                user_input = input(f"Enter release year for '{t.artist} - {t.title}' (or press Enter to skip): ").strip()
                if user_input.isdigit() and len(user_input) == 4:
                    entered_year = int(user_input)
                    t.year = entered_year
                    # Update cache record
                    t_hash = get_track_hash(t.artist, t.title)
                    if t_hash in cache:
                        cache[t_hash]["year"] = entered_year
                    else:
                        cache[t_hash] = {
                            "artist": t.artist,
                            "title": t.title,
                            "style": t.style,
                            "energy": t.energy,
                            "vocal_type": t.vocal_type,
                            "popularity_tier": t.popularity_tier,
                            "summary": t.summary,
                            "year": entered_year
                        }
            except (EOFError, KeyboardInterrupt):
                break
        save_cache(cache)
    
    return tracks

class SituationParameters(BaseModel):
    """
    Pydantic schema representing the adjusted options resolved by Gemini for a specific situation.
    """
    progression: str = Field(description="The closest standard progression profile matching the description: 'low-to-high', 'high-to-low', 'wave', 'u-shape', or 'custom'.")
    custom_progression: Optional[List[float]] = Field(description="If progression is 'custom', a list of exactly 10 target energy levels (values from 1.0 to 10.0) mapping the step-by-step energy curve of the set list.")
    weight_key: float = Field(description="Mismatch penalty weight for harmonic key compatibility (typically between 5.0 and 15.0).")
    weight_bpm: float = Field(description="Mismatch penalty weight for BPM differences (typically between 2.0 and 10.0).")
    weight_energy: float = Field(description="Mismatch penalty weight for target energy curve deviation (typically between 1.0 and 8.0).")
    weight_genre: float = Field(description="Mismatch penalty weight for subgenre style compatibility (typically between 1.0 and 8.0).")
    target_duration_minutes: Optional[int] = Field(None, description="If the user's description specifies or strongly implies a specific total duration of the set in minutes (e.g. '6 hours set' implies 360, '2h gig' implies 120, '45 mins set' implies 45), output it here as an integer. Otherwise, output null.")
    target_tracks_count: Optional[int] = Field(None, description="If the user's description specifies or strongly implies a specific track count (e.g. '15 track mix' implies 15, 'mix of 25 tracks' implies 25), output it here as an integer. Otherwise, output null.")
    min_year: Optional[int] = Field(None, description="If the situation specifies a decade, era, or year range (e.g. '90s' -> 1990, '80s' -> 1980, '2000s' -> 2000, '2010 to 2015' -> 2010), output the earliest year here. Otherwise, output null.")
    max_year: Optional[int] = Field(None, description="If the situation specifies a decade, era, or year range (e.g. '90s' -> 1999, '80s' -> 1989, '2000s' -> 2009, '2010 to 2015' -> 2015), output the latest year here. Otherwise, output null.")
    allow_consecutive_anthems: bool = Field(False, description="Set to true ONLY if the situation is explicitly a 'classics set', 'all-time anthems', or 'greatest hits' celebration where playing legendary anthems back-to-back is desired. Otherwise false.")
    explanation: str = Field(description="A brief human-readable explanation of why these parameters and energy curve were chosen for this mood/situation.")

def resolve_situation_parameters(situation: str, api_key: str) -> SituationParameters:
    """
    Query Gemini to analyze a human-like mood/situation and output optimized set parameters.
    """
    client = genai.Client(api_key=api_key)
    
    prompt = (
        f"Analyze the following DJ gig mood, context, or situation: '{situation}'\n\n"
        "Recommend the optimal transition penalty weights (key compatibility weight, BPM matching weight, "
        "energy matching weight, subgenre mismatch weight) and set progression. "
        "Also, if the text specifies or implies a set duration (e.g., '6 hours', '120 minutes') or track count (e.g., '15 tracks'), "
        "be sure to capture and parse that duration (in minutes) or track count as well. "
        "If the user specifies or implies a specific decade or era (e.g., '90s', '80s', 'early 2000s', '1995-2005'), "
        "capture the min_year and max_year boundary integers (e.g. '90s' -> min_year=1990, max_year=1999). "
        "If the user specifically asks for an all-out 'classics' or 'anthems' set, set allow_consecutive_anthems to true.\n\n"
        "For example, a smooth lounge gig needs perfect keys/subgenres, while a peak-time party might "
        "prioritize rapid energy boosts and less restrictive key matching. "
        "Be analytical and DJ-minded."
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a professional world-class club and festival DJ director. "
                    "You translate human situations, moods, and venues into exact mathematical pathfinder weights, energy profiles, and set sizes."
                ),
                response_mime_type="application/json",
                response_schema=SituationParameters,
                temperature=0.3,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        return SituationParameters.model_validate_json(response.text)
    except Exception as e:
        # Return a safe, standard default fallback
        return SituationParameters(
            progression="low-to-high",
            custom_progression=None,
            weight_key=10.0,
            weight_bpm=5.0,
            weight_energy=3.0,
            weight_genre=2.0,
            target_duration_minutes=None,
            target_tracks_count=None,
            explanation=f"Fallback to default parameters (error resolving situation: {e})"
        )
