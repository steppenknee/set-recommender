"""
Rekordbox DJ Set Recommender - Rekordbox XML Parser & Playlist Exporter
Filename: set_recommender/xml_handler.py

This module parses Rekordbox exported XML collection files, instantiates standard Track objects,
and safe-exports recommended sets by appending new playlist nodes. It guarantees that existing 
collection metadata, ratings, cue points, and beatgrids are preserved exactly as-is.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Tuple

class Track:
    """
    Data model representing a track parsed from Rekordbox XML database.
    
    Attributes:
        track_id (str): The unique database identifier assigned by Rekordbox.
        artist (str): The recording artist name.
        title (str): The song title.
        bpm (float): Beats-per-minute (tempo).
        key (str): Key signature (Camelot like '8A' or Traditional like 'Am').
        duration (int): Duration of the track in seconds.
        location (str): System URI location path of the physical audio file.
        genre (str): Generic genre provided by the Rekordbox library.
        year (int): Release year of the track (e.g. 1995, 2024). 0 if missing/unspecified.
        raw_element (xml.etree.ElementTree.Element): Original XML object for deep references.
        style (str): Refined electronic subgenre style (enriched by LLM).
        energy (int): Target intensity level from 1 (slow/deep) to 10 (aggressive peak).
    """
    def __init__(self, track_id: str, artist: str, title: str, bpm: float, key: str, duration: int, location: str, genre: str = "", rating: int = 0, year: int = 0, raw_element: ET.Element = None):
        self.track_id = track_id
        self.artist = artist
        self.title = title
        self.bpm = bpm
        self.key = key
        self.duration = duration  # Duration in seconds
        self.location = location
        self.genre = genre
        self.rating = rating      # Star rating (0 to 5)
        self.year = year          # Release year (e.g. 1995, 0 if unknown)
        self.raw_element = raw_element  # Holds XML element reference
        
        # Enriched attributes, populated during metadata step
        self.style = ""
        self.energy = 5  # Default medium intensity
        self.vocal_type = "instrumental"  # "full_vocal", "vocal_hook", or "instrumental"
        self.summary = ""  # 1-sentence vibe/timbre description
        self.popularity_tier = "underground"  # "anthem", "well_known", "underground", or "deep_cut"

    def __repr__(self) -> str:
        return f"<Track {self.track_id}: {self.artist} - {self.title} (BPM: {self.bpm}, Key: {self.key}, Energy: {self.energy}, Popularity: {self.popularity_tier})>"

def parse_rekordbox_xml(xml_path: Path) -> Tuple[List[Track], ET.ElementTree]:
    """
    Parse a Rekordbox-compatible XML database.
    
    Reads XML nodes, processes standard track fields, and wraps them in a list 
    of Track models. Preserves the full XML DOM tree structure for exporting.
    
    Args:
        xml_path (Path): Filepath to the source Rekordbox .xml file.
        
    Returns:
        Tuple[List[Track], ET.ElementTree]:
            - List of Track elements in the master library.
            - The original ElementTree instance used to rewrite.
            
    Raises:
        ValueError: If the XML is missing the master <COLLECTION> element.
    """
    # Parse the XML file into memory
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    tracks = []
    
    # Locate the master <COLLECTION> tag containing physical tracks
    collection = root.find("COLLECTION")
    if collection is None:
        raise ValueError("Invalid Rekordbox XML: No <COLLECTION> node found.")
        
    # Read each track entry and capture its attributes
    for track_elem in collection.findall("TRACK"):
        track_id = track_elem.get("TrackID", "")
        artist = track_elem.get("Artist", "Unknown Artist")
        title = track_elem.get("Name", "Unknown Track")
        
        # Parse BPM safely (supports both AverageBpm and BPM, falls back to 0.0)
        bpm_str = track_elem.get("AverageBpm") or track_elem.get("BPM") or "0.0"
        try:
            bpm = float(bpm_str)
        except ValueError:
            bpm = 0.0
            
        # Parse key signature (supports both Tonality and Key)
        key = track_elem.get("Tonality") or track_elem.get("Key") or ""
        
        # Parse duration safely (falls back to 0 on error)
        duration_str = track_elem.get("TotalTime", "0")
        try:
            duration = int(duration_str)
        except ValueError:
            duration = 0
            
        location = track_elem.get("Location", "")
        genre = track_elem.get("Genre", "")
        
        # Parse rating (supports standard Rekordbox 0-255 rating, converts to 0-5 stars)
        rating_str = track_elem.get("Rating", "0")
        try:
            raw_rating = int(rating_str)
        except ValueError:
            raw_rating = 0
            
        if raw_rating >= 255:
            rating = 5
        elif raw_rating >= 204:
            rating = 4
        elif raw_rating >= 153:
            rating = 3
        elif raw_rating >= 102:
            rating = 2
        elif raw_rating >= 51:
            rating = 1
        else:
            rating = 0
            
        # Parse year safely (falls back to 0 on error/missing)
        year_str = track_elem.get("Year", "0")
        try:
            year = int(year_str)
        except ValueError:
            year = 0
            
        # Wrap into standard Track class
        track_obj = Track(
            track_id=track_id,
            artist=artist,
            title=title,
            bpm=bpm,
            key=key,
            duration=duration,
            location=location,
            genre=genre,
            rating=rating,
            year=year,
            raw_element=track_elem
        )
        tracks.append(track_obj)
        
    return tracks, tree

def save_recommended_xml(
    original_tree: ET.ElementTree, 
    recommended_tracks: List[Track], 
    playlist_name: str, 
    output_path: Path
):
    """
    Write recommended playlist sequence back into Rekordbox XML structure.
    
    Copies and preserves original <COLLECTION> records intact, and injects a 
    brand new <NODE Type="1"> (Playlist) referencing track IDs in their calculated 
    mixing order under the <PLAYLISTS> root.
    
    Args:
        original_tree (ET.ElementTree): The loaded DOM tree of the original XML file.
        recommended_tracks (List[Track]): Ordered list of recommended tracks.
        playlist_name (str): The visual name of the playlist to show in Rekordbox.
        output_path (Path): Filepath where the new XML file will be saved.
    """
    root = original_tree.getroot()
    
    # Locate or establish the <PLAYLISTS> root folder tree
    playlists_elem = root.find("PLAYLISTS")
    if playlists_elem is None:
        playlists_elem = ET.SubElement(root, "PLAYLISTS")
        
    # Search for or insert the master ROOT node (Type="0" = folder)
    root_node = None
    for node in playlists_elem.findall("NODE"):
        if node.get("Type") == "0" and node.get("Name") == "ROOT":
            root_node = node
            break
            
    if root_node is None:
        root_node = ET.SubElement(playlists_elem, "NODE", Type="0", Name="ROOT", Count="0")
        
    entries_count = len(recommended_tracks)
    
    # Establish a new playlist node (Type="1" = Playlist)
    new_playlist_node = ET.SubElement(
        root_node, 
        "NODE", 
        Type="1", 
        Name=playlist_name, 
        Entries=str(entries_count)
    )
    
    # Inject each track reference node (identified by Key="[TrackID]")
    for track in recommended_tracks:
        ET.SubElement(new_playlist_node, "TRACK", Key=track.track_id)
        
    # Update the parent folder node count (number of sub-playlists/folders)
    current_count = int(root_node.get("Count", "0"))
    root_node.set("Count", str(current_count + 1))
    
    # Write the entire XML content back out
    original_tree.write(
        output_path, 
        encoding="UTF-8", 
        xml_declaration=True
    )
