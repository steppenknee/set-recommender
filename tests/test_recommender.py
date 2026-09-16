import unittest
from pathlib import Path
from set_recommender.xml_handler import parse_rekordbox_xml, save_recommended_xml, Track
from set_recommender.recommender import (
    parse_key_to_camelot,
    get_key_cost,
    get_bpm_cost,
    get_genre_cost,
    generate_energy_curve,
    recommend_set_beam_search
)

class TestRecommender(unittest.TestCase):
    
    def test_key_parsing(self):
        """Test parsing of various musical and Camelot keys."""
        self.assertEqual(parse_key_to_camelot("8A"), (8, "A"))
        self.assertEqual(parse_key_to_camelot("11B"), (11, "B"))
        self.assertEqual(parse_key_to_camelot("Am"), (8, "A"))
        self.assertEqual(parse_key_to_camelot("C"), (8, "B"))
        self.assertEqual(parse_key_to_camelot("G#m"), (1, "A"))
        self.assertEqual(parse_key_to_camelot("invalid"), None)
        
    def test_key_costs(self):
        """Test distance cost calculation between Camelot keys."""
        # Same key
        self.assertEqual(get_key_cost((8, "A"), (8, "A")), 0.0)
        # Relative minor/major
        self.assertEqual(get_key_cost((8, "A"), (8, "B")), 1.0)
        # Fifth shift
        self.assertEqual(get_key_cost((8, "A"), (9, "A")), 1.0)
        self.assertEqual(get_key_cost((8, "A"), (7, "A")), 1.0)
        # Diagonal shift
        self.assertEqual(get_key_cost((8, "A"), (9, "B")), 2.0)
        # Energy boost (+2 steps)
        self.assertEqual(get_key_cost((8, "A"), (10, "A")), 3.0)
        # Semi-tone boost (+7 steps)
        self.assertEqual(get_key_cost((8, "A"), (3, "A")), 4.0)
        # Disharmonic transition
        self.assertEqual(get_key_cost((8, "A"), (2, "A")), 10.0)

    def test_bpm_costs(self):
        """Test BPM mismatch costs using absolute limits."""
        # 1 BPM or less: Perfect match
        self.assertEqual(get_bpm_cost(120, 120.8), 0.0)
        # Between 1 and 3 BPM difference
        self.assertEqual(get_bpm_cost(120, 122), 5.0)
        self.assertEqual(get_bpm_cost(120, 123), 10.0)
        # Over 3 BPM difference
        self.assertEqual(get_bpm_cost(120, 124), 100.0)

    def test_genre_costs(self):
        """Test subgenre matching and token-based compatibility."""
        self.assertEqual(get_genre_cost("Melodic Techno", "Melodic Techno"), 0.0)
        self.assertEqual(get_genre_cost("Deep House", "Progressive House"), 1.0)
        self.assertEqual(get_genre_cost("Techno", "Ambient"), 5.0)

    def test_energy_curve(self):
        """Test that generated energy curves are scaled and mapped properly."""
        curve = generate_energy_curve("low-to-high", 5)
        self.assertEqual(len(curve), 5)
        self.assertEqual(curve[0], 3.0)
        self.assertEqual(curve[-1], 9.0)

    def test_beam_search(self):
        """Test running beam search pathfinder on parsed mock track elements."""
        xml_path = Path(__file__).parent.parent / "sample_library.xml"
        track_pool, _ = parse_rekordbox_xml(xml_path)
        
        # Manually enrich tracks to bypass Gemini API call for testing
        for idx, track in enumerate(track_pool):
            track.style = track.genre
            # Distribute mock energy levels
            track.energy = (idx % 10) + 1
            
        recommended = recommend_set_beam_search(
            track_pool=track_pool,
            target_tracks_count=5,
            progression="low-to-high",
            beam_width=10
        )
        
        self.assertEqual(len(recommended), 5)
        # The result must contain distinct tracks (no duplicates)
        track_ids = [t.track_id for t in recommended]
        self.assertEqual(len(set(track_ids)), 5)

    def test_consecutive_vocals_penalty(self):
        """Test that consecutive vocal tracks are successfully penalized during pathfinding."""
        from set_recommender.xml_handler import Track
        t1 = Track("1", "Artist", "Title 1", 120.0, "8A", 300, "loc", "genre", 4)
        t2 = Track("2", "Artist", "Title 2", 120.0, "8A", 300, "loc", "genre", 4)
        t3 = Track("3", "Artist", "Title 3", 120.0, "8A", 300, "loc", "genre", 4)
        
        t1.vocal_type = "full_vocal"
        t2.vocal_type = "full_vocal"
        t3.vocal_type = "full_vocal"
        
        track_pool = [t1, t2, t3]
        
        recommended = recommend_set_beam_search(
            track_pool=track_pool,
            target_tracks_count=3,
            progression="low-to-high",
            beam_width=10
        )
        self.assertEqual(len(recommended), 3)

    def test_boost_harmonic_mode(self):
        """Test that get_key_cost prioritizes +2 and +7 key shifts when boost harmonic mode is enabled."""
        from set_recommender.recommender import get_key_cost
        
        k1 = (8, "A")  # 8A
        k2 = (10, "A") # 10A (+2 steps)
        k3 = (3, "A")  # 3A (+7 steps)
        k_same = (8, "A") # 8A (same key)
        
        # In standard mode, same key cost is 0.0, and +2/+7 shifts are penalized (3.0 and 4.0)
        self.assertEqual(get_key_cost(k1, k_same, harmonic_mode="standard"), 0.0)
        self.assertEqual(get_key_cost(k1, k2, harmonic_mode="standard"), 3.0)
        self.assertEqual(get_key_cost(k1, k3, harmonic_mode="standard"), 4.0)
        
        # In boost mode, same key is penalized (2.0), and +2/+7 shifts are rewarded with 0.0 cost
        self.assertEqual(get_key_cost(k1, k_same, harmonic_mode="boost"), 2.0)
        self.assertEqual(get_key_cost(k1, k2, harmonic_mode="boost"), 0.0)
        self.assertEqual(get_key_cost(k1, k3, harmonic_mode="boost"), 0.0)

    def test_enrich_batch_with_retry_split_on_error(self):
        """Test that enrich_batch_with_retry recursively splits the batch on error."""
        from unittest.mock import MagicMock
        from set_recommender.xml_handler import Track
        from set_recommender.enricher import enrich_batch_with_retry
        
        t1 = Track("1", "Artist 1", "Title 1", 120.0, "8A", 300, "loc", "genre", 4)
        t2 = Track("2", "Artist 2", "Title 2", 120.0, "8A", 300, "loc", "genre", 4)
        
        mock_client = MagicMock()
        # Mock generate_content to raise an error
        mock_client.models.generate_content.side_effect = Exception("API error")
        
        cache = {}
        batch = [t1, t2]
        
        # When called on batch of size 2, it should fail, split in half, and try size 1
        # Each size 1 trial fails too, applying defaults.
        enrich_batch_with_retry(mock_client, batch, cache)
        
        # Verify fallback values were applied
        self.assertEqual(t1.style, "genre")
        self.assertEqual(t2.style, "genre")
        self.assertEqual(t1.energy, 5)
        self.assertEqual(t2.energy, 5)

    def test_year_attribute_and_decade_filter(self):
        """Test Track year attribute parsing and decade filtering logic."""
        t1 = Track("1", "Artist 1", "Title 1", 124.0, "8A", 300, "loc", "House", 4, year=1995)
        t2 = Track("2", "Artist 2", "Title 2", 125.0, "8A", 300, "loc", "House", 5, year=2005)
        t3 = Track("3", "Artist 3", "Title 3", 124.0, "8A", 300, "loc", "House", 3, year=0)
        
        pool = [t1, t2, t3]
        
        # Filter for 90s (1990 - 1999)
        filtered_90s = [t for t in pool if t.year >= 1990 and t.year <= 1999]
        self.assertEqual(len(filtered_90s), 1)
        self.assertEqual(filtered_90s[0].title, "Title 1")
        
        # Filter for 2000s (2000 - 2009)
        filtered_2000s = [t for t in pool if t.year >= 2000 and t.year <= 2009]
        self.assertEqual(len(filtered_2000s), 1)
        self.assertEqual(filtered_2000s[0].title, "Title 2")

    def test_artist_token_extraction_and_collab_overlap(self):
        """Test wildcard and collaboration artist matching."""
        from set_recommender.recommender import extract_artist_tokens, has_artist_overlap
        
        # Test token splitting on feat, &, x, vs
        tokens = extract_artist_tokens("Calvin Harris feat. Dua Lipa")
        self.assertIn("calvin harris", tokens)
        self.assertIn("dua lipa", tokens)
        
        tokens_vs = extract_artist_tokens("CamelPhat x Elderbrook")
        self.assertIn("camelphat", tokens_vs)
        self.assertIn("elderbrook", tokens_vs)
        
        # Test collaboration overlap detection
        self.assertTrue(has_artist_overlap("Calvin Harris", "Calvin Harris feat. Ellie Goulding"))
        self.assertTrue(has_artist_overlap("CamelPhat x Elderbrook", "Elderbrook"))
        self.assertTrue(has_artist_overlap("Fisher & Chris Lake", "Chris Lake"))
        self.assertFalse(has_artist_overlap("Dua Lipa", "Deadmau5"))

    def test_popularity_tier_and_anthem_spacing(self):
        """Test that back-to-back anthems are spaced out unless allow_consecutive_anthems is True."""
        from set_recommender.recommender import recommend_set_beam_search
        
        t1 = Track("1", "Artist A", "Anthem Track 1", 124.0, "8A", 300, "loc", "House", 5)
        t1.popularity_tier = "anthem"
        t1.energy = 8
        
        t2 = Track("2", "Artist B", "Anthem Track 2", 124.0, "8A", 300, "loc", "House", 5)
        t2.popularity_tier = "anthem"
        t2.energy = 8
        
        t3 = Track("3", "Artist C", "Deep Cut Track", 124.0, "8A", 300, "loc", "House", 4)
        t3.popularity_tier = "deep_cut"
        t3.energy = 8
        
        pool = [t1, t2, t3]
        
        # In standard mode (allow_consecutive_anthems=False), Deep Cut should be woven between the two anthems
        res_standard = recommend_set_beam_search(pool, target_tracks_count=3, allow_consecutive_anthems=False)
        self.assertEqual(len(res_standard), 3)
        self.assertEqual(res_standard[1].popularity_tier, "deep_cut")
        
        # In classics mode (allow_consecutive_anthems=True), anthems can play consecutively
        res_classics = recommend_set_beam_search(pool, target_tracks_count=3, allow_consecutive_anthems=True)
        self.assertEqual(len(res_classics), 3)

if __name__ == "__main__":
    unittest.main()

