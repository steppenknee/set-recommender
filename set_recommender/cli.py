"""
Rekordbox DJ Set Recommender - Interactive Command-Line Interface
Filename: set_recommender/cli.py

This module contains the console command parsing interface powered by Typer and Rich.
It parses parameters, handles API configuration validation, coordinates metadata lookups, 
triggers the recommendation pathfinder, and prints details using Rich progress screens 
and console tables.
"""

import typer
import math
from pathlib import Path
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from set_recommender.config import get_api_key, save_config, CONFIG_FILE
from set_recommender.xml_handler import parse_rekordbox_xml, save_recommended_xml
from set_recommender.enricher import enrich_tracks, resolve_situation_parameters
from set_recommender.recommender import recommend_set_beam_search, parse_key_to_camelot

# Initialize Console and Typer instance
app = typer.Typer(help="Rekordbox DJ Set Recommender CLI - Create harmonically and rhythmically optimized set lists.")
console = Console()

def format_duration(seconds: int) -> str:
    """
    Format seconds into MM:SS.
    
    Args:
        seconds (int): Seconds.
        
    Returns:
        str: Formatted time string.
    """
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"

def validate_and_get_api_key(override_key: Optional[str]) -> str:
    """
    Validate the presence of a Gemini API key. Prompts the user interactively 
    if no key is configured, saving it to config.json.
    
    Args:
        override_key (str, optional): Key provided as CLI flag override.
        
    Returns:
        str: Validated Gemini API key.
        
    Raises:
        typer.Exit: Exits with status 1 if key validation fails.
    """
    key = get_api_key(override_key)
    if not key:
        rprint("[bold yellow]Gemini API key not found![/bold yellow]")
        rprint("We need a Gemini API key to enrich track metadata (style and energy).")
        rprint(f"You can also set this via the [bold]GEMINI_API_KEY[/bold] environment variable.")
        
        prompted_key = typer.prompt("Please enter your Gemini API key", hide_input=True)
        if prompted_key:
            save_config({"GEMINI_API_KEY": prompted_key})
            rprint(f"[green]Key saved successfully to {CONFIG_FILE}[/green]\n")
            key = prompted_key
        else:
            rprint("[bold red]Error: Gemini API key is required to proceed.[/bold red]")
            raise typer.Exit(code=1)
    return key

@app.command("enrich")
def enrich_cmd(
    input_xml: Path = typer.Argument(..., help="Path to the source Rekordbox XML file.", exists=True, file_okay=True, dir_okay=False, readable=True),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Gemini API Key override."),
    batch_size: int = typer.Option(20, "--batch-size", "-b", help="Number of tracks to process per API call."),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-fetching from Gemini even if already cached.")
):
    """
    Query the Gemini API to find track electronic subgenres and energy levels and populate your local cache.
    """
    key = validate_and_get_api_key(api_key)
    
    rprint(f"[bold blue]Parsing Rekordbox XML:[/bold blue] {input_xml}")
    try:
        tracks, _ = parse_rekordbox_xml(input_xml)
    except Exception as e:
        rprint(f"[bold red]Error parsing XML:[/bold red] {e}")
        raise typer.Exit(code=1)
        
    rprint(f"Found {len(tracks)} tracks in the collection.")
    
    # Run enrichment step
    enrich_tracks(tracks, api_key=key, batch_size=batch_size, force=force)
    
    rprint("[bold green]Success![/bold green] All tracks parsed and cached successfully.")

@app.command("recommend")
def recommend_cmd(
    input_xml: Path = typer.Argument(..., help="Path to the source Rekordbox XML file.", exists=True, file_okay=True, dir_okay=False, readable=True),
    output_xml: Path = typer.Argument(..., help="Target path to save the recommended Rekordbox XML file."),
    tracks: Optional[int] = typer.Option(None, "--tracks", "-t", help="Number of tracks to include in the recommended set."),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="Target set duration in minutes."),
    progression: str = typer.Option("low-to-high", "--progression", "-p", help="Energy profile progression preset: low-to-high, high-to-low, wave, u-shape."),
    custom_progression: Optional[str] = typer.Option(None, "--custom-progression", help="Comma-separated target energy profile (e.g. '3,4,6,5,8,9,7'). Overrides preset."),
    playlist_name: str = typer.Option("Recommended DJ Set", "--playlist-name", help="Name of the playlist node generated in Rekordbox."),
    weight_key: float = typer.Option(10.0, "--weight-key", help="Mismatch penalty weight for harmonic key compatibility."),
    weight_bpm: float = typer.Option(5.0, "--weight-bpm", help="Mismatch penalty weight for BPM differences."),
    weight_energy: float = typer.Option(3.0, "--weight-energy", help="Mismatch penalty weight for target energy curve deviation."),
    weight_genre: float = typer.Option(2.0, "--weight-genre", help="Mismatch penalty weight for subgenre style compatibility."),
    weight_rating: float = typer.Option(2.0, "--weight-rating", help="Priority bonus weight for higher-rated tracks."),
    beam_width: int = typer.Option(50, "--beam-width", help="Beam width for optimization lookahead pathfinding."),
    transition_overlap: int = typer.Option(60, "--transition-overlap", help="Estimated average overlap transition/blend time in seconds between consecutive tracks."),
    situation: Optional[str] = typer.Option(None, "--situation", "-s", help="A human-like mood or situation description (e.g. 'early evening bar', '90s party') to dynamically configure set parameters using Gemini."),
    harmonic_mode: str = typer.Option("standard", "--harmonic-mode", help="Harmonic mixing mode: 'standard' (smooth blended keys) or 'boost' (prioritizes energetic +2 and +7 Camelot wheel shifts)."),
    classics: bool = typer.Option(False, "--classics", help="Allow back-to-back anthems / stone-cold classics (ideal for greatest-hits and classics sets)."),
    decade: Optional[str] = typer.Option(None, "--decade", help="Filter tracks by decade (e.g. '80s', '90s', '2000s', '2010s', '2020s')."),
    year_min: Optional[int] = typer.Option(None, "--year-min", help="Filter tracks released on or after this year."),
    year_max: Optional[int] = typer.Option(None, "--year-max", help="Filter tracks released on or before this year."),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Gemini API Key override.")
):
    """
    Generate an optimized DJ set list playlist and save it into a new Rekordbox XML.
    """
    # 1. Mutually exclusive option validations
    if tracks is not None and duration is not None:
        rprint("[bold red]Error: Cannot specify both --tracks and --duration options. Please select only one.[/bold red]")
        raise typer.Exit(code=1)
        
    # 2. Key validation and rehydration
    key = validate_and_get_api_key(api_key)
    
    # 3. XML Parsing
    rprint(f"[bold blue]Parsing Rekordbox XML:[/bold blue] {input_xml}")
    try:
        track_pool, xml_tree = parse_rekordbox_xml(input_xml)
    except Exception as e:
        rprint(f"[bold red]Error parsing XML:[/bold red] {e}")
        raise typer.Exit(code=1)
        
    if not track_pool:
        rprint("[bold red]Error: The input Rekordbox collection is empty.[/bold red]")
        raise typer.Exit(code=1)
        
    rprint(f"Loaded {len(track_pool)} tracks from database.")
    
    # 4. Enrich/populate track metadata (reads automatically from cache, or prompts api if missing)
    rprint("[bold blue]Checking metadata cache & enriching missing track info...[/bold blue]")
    enrich_tracks(track_pool, api_key=key, force=False)
    
    # 5. Handle Situation analysis and dynamic configuration
    parsed_custom: Optional[List[float]] = None
    if situation:
        rprint(f"[bold magenta]🤖 Analyzing situation with Gemini:[/bold magenta] '{situation}'")
        try:
            situation_params = resolve_situation_parameters(situation, key)
            rprint(f"\n[bold cyan]💡 Situation Assessment:[/bold cyan] {situation_params.explanation}")
            
            # Override default weights with situation-derived weights unless explicitly changed by CLI options
            if weight_key == 10.0:
                weight_key = situation_params.weight_key
            if weight_bpm == 5.0:
                weight_bpm = situation_params.weight_bpm
            if weight_energy == 3.0:
                weight_energy = situation_params.weight_energy
            if weight_genre == 2.0:
                weight_genre = situation_params.weight_genre
                
            if progression == "low-to-high" and not custom_progression:
                if situation_params.progression == "custom" and situation_params.custom_progression:
                    parsed_custom = situation_params.custom_progression
                    rprint(f"[bold white]Dynamic Progression:[/bold white] custom ({','.join(str(x) for x in parsed_custom)})")
                else:
                    progression = situation_params.progression
                    rprint(f"[bold white]Dynamic Progression preset:[/bold white] {progression}")
            else:
                rprint(f"[bold yellow]Note: Preserving explicit CLI progression: {custom_progression if custom_progression else progression}[/bold yellow]")
                
            # If the user didn't specify tracks or duration on the command line, resolve from situation
            if tracks is None and duration is None:
                if situation_params.target_duration_minutes:
                    duration = situation_params.target_duration_minutes
                    rprint(f"[bold white]Dynamic Target Duration:[/bold white] {duration} minutes (parsed from situation)")
                elif situation_params.target_tracks_count:
                    tracks = situation_params.target_tracks_count
                    rprint(f"[bold white]Dynamic Target Track Count:[/bold white] {tracks} tracks (parsed from situation)")
                    
            # If decade/era constraints were detected in the situation, adopt them unless overridden
            if situation_params.min_year and year_min is None and decade is None:
                year_min = situation_params.min_year
                rprint(f"[bold white]Dynamic Min Year:[/bold white] {year_min} (parsed from situation)")
            if situation_params.max_year and year_max is None and decade is None:
                year_max = situation_params.max_year
                rprint(f"[bold white]Dynamic Max Year:[/bold white] {year_max} (parsed from situation)")
            if situation_params.allow_consecutive_anthems:
                classics = True
                rprint("[bold green]Dynamic Classics Mode:[/bold green] Enabled (back-to-back anthems allowed)")
                
            rprint(f"[bold white]Dynamic Pathfinder Weights:[/bold white] Key: {weight_key:.1f} | BPM: {weight_bpm:.1f} | Energy: {weight_energy:.1f} | Genre: {weight_genre:.1f} | Rating: {weight_rating:.1f}\n")
        except Exception as e:
            rprint(f"[bold yellow][Warning] Failed to resolve situation parameters: {e}. Falling back to standard settings.[/bold yellow]")

    # 5.1. Handle explicit decade flag (e.g. '90s', '80s', '2000s')
    if decade:
        d_clean = decade.strip().lower()
        if "70" in d_clean:
            year_min, year_max = 1970, 1979
        elif "80" in d_clean:
            year_min, year_max = 1980, 1989
        elif "90" in d_clean:
            year_min, year_max = 1990, 1999
        elif "2000" in d_clean or "00" in d_clean:
            year_min, year_max = 2000, 2009
        elif "2010" in d_clean or "10" in d_clean:
            year_min, year_max = 2010, 2019
        elif "2020" in d_clean or "20" in d_clean:
            year_min, year_max = 2020, 2029

    # 5.2. Filter candidate track pool based on year constraints if active
    if year_min is not None or year_max is not None:
        filtered_pool = []
        for t in track_pool:
            # If track year is unknown (0), we exclude if strict filtering is active
            if t.year > 0:
                if year_min is not None and t.year < year_min:
                    continue
                if year_max is not None and t.year > year_max:
                    continue
                filtered_pool.append(t)
            else:
                # Track has no year metadata
                continue
                
        if not filtered_pool:
            rprint(f"[bold red]Error: No tracks in library match the requested year range ({year_min or 'Any'} - {year_max or 'Any'}).[/bold red]")
            raise typer.Exit(code=1)
            
        rprint(f"[bold green]Applied Year Filter ({year_min or 'Any'} - {year_max or 'Any'}):[/bold green] Filtered pool from {len(track_pool)} ➔ {len(filtered_pool)} tracks.")
        track_pool = filtered_pool

    # If neither tracks nor duration is specified (by CLI or situation), fall back to default track count of 10
    if tracks is None and duration is None:
        tracks = 10
        rprint("[bold white]Default Target Track Count:[/bold white] 10 tracks\n")

    # If duration was specified (directly or dynamically), convert to tracks count
    if duration is not None and tracks is None:
        # Estimate track count (assuming average 5 min track length with 1 min transition overlap -> 4 mins per track)
        estimated_tracks = max(3, int((duration * 60) / 240))
        rprint(f"[bold white]Target Duration {duration} minutes maps to approx {estimated_tracks} tracks.[/bold white]")
        tracks = estimated_tracks
        duration = None  # Force track count mode for exact rounded buffer planning

    # Apply professional rounding to nearest 5 with extra backup buffer
    if tracks is not None:
        original_tracks = tracks
        rounded_tracks = math.ceil(original_tracks / 5) * 5
        if rounded_tracks == original_tracks:
            rounded_tracks += 5
        
        # Ensure we don't exceed the total track pool size
        rounded_tracks = min(rounded_tracks, len(track_pool))
        
        rprint(f"[bold green]Rounding up track count to nearest 5 with backup buffer: {original_tracks} ➔ {rounded_tracks} tracks.[/bold green]\n")
        tracks = rounded_tracks

    # 5.5. Parse Custom Progression if explicitly provided on command line
    if custom_progression:
        try:
            parsed_custom = [float(x.strip()) for x in custom_progression.split(",")]
        except ValueError:
            rprint("[bold red]Error: Custom progression must be a comma-separated list of numbers, e.g. '3,4,6,5,8,9,7'.[/bold red]")
            raise typer.Exit(code=1)
            
    # 6. Recommendation Search
    rprint("[bold blue]Calculating optimized set list via Beam Search pathfinder...[/bold blue]")
    recommended = recommend_set_beam_search(
        track_pool=track_pool,
        target_tracks_count=tracks,
        target_duration_minutes=duration,
        progression=progression,
        custom_progression=parsed_custom,
        w_key=weight_key,
        w_bpm=weight_bpm,
        w_energy=weight_energy,
        w_genre=weight_genre,
        w_rating=weight_rating,
        beam_width=beam_width,
        overlap_seconds=transition_overlap,
        harmonic_mode=harmonic_mode,
        allow_consecutive_anthems=classics
    )
    
    if not recommended:
        rprint("[bold red]Error: Pathfinder was unable to calculate a valid transition path.[/bold red]")
        raise typer.Exit(code=1)
        
    # 7. Render a beautiful CLI Table of Recommended Playlist
    table = Table(title=f"🎧 Recommended DJ Set List: '{playlist_name}'", title_style="bold magenta")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Artist", style="green")
    table.add_column("Title", style="white")
    table.add_column("Year", justify="center", style="dim cyan")
    table.add_column("BPM", justify="right", style="yellow")
    table.add_column("Key (Camelot)", justify="center", style="blue")
    table.add_column("Subgenre Style", style="magenta")
    table.add_column("Popularity", justify="center")
    table.add_column("Rating", justify="center", style="bold yellow")
    table.add_column("Vocals", justify="center")
    table.add_column("Energy", justify="right", style="bold red")
    table.add_column("Length", justify="right", style="cyan")
    
    total_seconds = 0
    total_energy = 0.0
    clashes = []
    
    for idx, track in enumerate(recommended):
        camelot_key = track.key
        parsed_k = parse_key_to_camelot(track.key)
        if parsed_k:
            camelot_key = f"{parsed_k[0]}{parsed_k[1]}"
            
        rating_stars = "⭐" * track.rating if track.rating > 0 else "[dim]-[/dim]"
        year_str = str(track.year) if track.year and track.year > 0 else "[dim]-[/dim]"
        
        # Popularity badge styling
        if track.popularity_tier == "anthem":
            pop_display = "[bold yellow]🔥 Anthem[/bold yellow]"
        elif track.popularity_tier == "well_known":
            pop_display = "[bold cyan]Hit[/bold cyan]"
        elif track.popularity_tier == "deep_cut":
            pop_display = "[dim magenta]Deep Cut[/dim magenta]"
        else:
            pop_display = "[dim]Underground[/dim]"
        
        # Style vocal presence tag nicely and flag consecutive full-vocal clashes
        vocal_display = "[dim]-[/dim]"
        if track.vocal_type == "full_vocal":
            if idx > 0 and recommended[idx-1].vocal_type == "full_vocal":
                vocal_display = "[bold pink]vocal[/bold pink] [bold orange](⚠️ Clash)[/bold orange]"
                clashes.append(idx + 1)
            else:
                vocal_display = "[bold pink]vocal[/bold pink]"
        elif track.vocal_type == "vocal_hook":
            vocal_display = "[cyan]hook[/cyan]"
        elif track.vocal_type == "instrumental":
            vocal_display = "[dim]inst[/dim]"
            
        table.add_row(
            str(idx + 1),
            track.artist,
            track.title,
            year_str,
            f"{track.bpm:.2f}",
            camelot_key,
            track.style,
            pop_display,
            rating_stars,
            vocal_display,
            str(track.energy),
            format_duration(track.duration)
        )
        total_seconds += track.duration
        total_energy += track.energy
        
    console.print(table)
    
    # Display set characteristics
    avg_energy = total_energy / len(recommended)
    actual_seconds = max(0, total_seconds - (len(recommended) - 1) * transition_overlap)
    rprint(f"[bold white]Total Tracks:[/bold white] {len(recommended)}")
    rprint(f"[bold white]Raw Track Sum Duration:[/bold white] {format_duration(total_seconds)} (approx. {total_seconds/60:.1f} minutes)")
    rprint(f"[bold white]Estimated Continuous Playtime:[/bold white] {format_duration(actual_seconds)} (approx. {actual_seconds/60:.1f} minutes) [dim](assuming {transition_overlap}s transition overlaps)[/dim]")
    rprint(f"[bold white]Average Set Energy:[/bold white] {avg_energy:.1f}/10")
    
    # Render vocal collision warnings if any clashes were identified
    if clashes:
        clash_str = ", ".join(f"#{c}" for c in clashes)
        rprint(f"\n[bold orange]⚠️ Vocal Collision Warning:[/bold orange] Sequential full-vocal overlap detected on tracks: {clash_str}.")
        rprint("[bold yellow]👉 DJ Advice:[/bold yellow] Consider loop-blending or drop-cutting during these transitions to avoid overlapping lyric sections.")
    
    # 8. Exporting back to a Rekordbox XML
    rprint(f"\n[bold blue]Saving playlist to XML:[/bold blue] {output_xml}")
    try:
        save_recommended_xml(xml_tree, recommended, playlist_name, output_xml)
        rprint("[bold green]Success![/bold green] Your set list has been successfully exported.")
        rprint("You can now import this file as a rekordbox xml database inside Rekordbox.")
    except Exception as e:
        rprint(f"[bold red]Error saving output XML:[/bold red] {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
