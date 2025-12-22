#!/usr/bin/env python3
"""
Test script to verify normalization functions work correctly
Uses the actual Dec 16 Hanukkah transcript as test case
"""

import re
import json
from typing import List, Dict, Optional, Tuple

# Import the normalization functions
import sys
sys.path.insert(0, '/Users/alexandermiron/Downloads/mention-markets')
from rollcall_sync import normalize_speaker_label, strip_rollcall_artifacts, normalize_transcript_format

# Sample raw data from Dec 16 Hanukkah transcript (user's example)
SAMPLE_RAW_TEXT = """Donald Trump Attends a Hanukkah Reception at the White House - December 16, 2025 StressLens 3 Topics 8 Entities Moderation 7 Speakers Full Transcript:

Donald Trump 00
00:00-00:00:10 (10 sec)

NO STRESSLENS:
Well, thank you very much. Nice place. I guess you've mostly been here, but -- [Audience members call out "We love you"]

Donald Trump 00
00:10-00:00:50 (40 sec)

NO SIGNAL (0.125):
-- you like it a lot better with Trump than you like it with Biden. That I can tell you. That's because you're smart. Well, I'm thrilled to welcome so many good friends to the White House as we celebrate the third night of Hanukkah. Third night. Time, time flies. Let me take a moment to send the love and prayers to our entire nation, to the people of Australia, and especially all those affected by the horrific and anti-Semitic terrorist attack, and that's exactly what it is, anti-Semitic.

Mark Levin 00
04:46-00:04:50 (4 sec)

NO STRESSLENS:
Hold on. [Audience members call out "Amen"]

Mark Levin 00
04:50-00:04:52 (2 sec)

NO STRESSLENS:
And he loves Israel too."""

def test_speaker_normalization():
    """Test speaker label normalization"""
    print("\n" + "="*80)
    print("TEST 1: Speaker Label Normalization")
    print("="*80)
    
    test_cases = [
        "Donald Trump 00",
        "Mark Levin 00",
        "Donald Trump (00:10:12)",
        "Donald Trump:",
        "Donald Trump",
        "Miriam Adelson 00",
        "Note 00"
    ]
    
    for raw in test_cases:
        normalized, was_modified = normalize_speaker_label(raw)
        status = "✅ FIXED" if was_modified else "✓ Already clean"
        print(f"{status}: '{raw}' -> '{normalized}'")

def test_artifact_stripping():
    """Test artifact removal from full text"""
    print("\n" + "="*80)
    print("TEST 2: Artifact Stripping")
    print("="*80)
    
    cleaned, stats = strip_rollcall_artifacts(SAMPLE_RAW_TEXT)
    
    print(f"\nOriginal length: {len(SAMPLE_RAW_TEXT)} chars")
    print(f"Cleaned length: {len(cleaned)} chars")
    print(f"Reduction: {len(SAMPLE_RAW_TEXT) - len(cleaned)} chars ({(1 - len(cleaned)/len(SAMPLE_RAW_TEXT))*100:.1f}%)")
    
    print(f"\nRemoval Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\nCleaned text preview (first 500 chars):")
    print("-" * 80)
    print(cleaned[:500])
    print("-" * 80)
    
    # Check if bad patterns still exist
    print(f"\nValidation Checks:")
    has_timestamps = bool(re.search(r'\d{1,2}:\d{2}-\d{1,2}:\d{2}:\d{2}', cleaned))
    has_ratings = bool(re.search(r'NO SIGNAL|NO STRESSLENS|MEDIUM|WEAK', cleaned))
    has_numeric_suffixes = bool(re.search(r'Trump\s+\d{2}', cleaned))
    has_boilerplate = bool(re.search(r'CAPITOL HILL SINCE|StressLens', cleaned))
    
    print(f"  Contains timestamps: {'❌ FAIL' if has_timestamps else '✅ PASS'}")
    print(f"  Contains ratings: {'❌ FAIL' if has_ratings else '✅ PASS'}")
    print(f"  Contains numeric suffixes: {'❌ FAIL' if has_numeric_suffixes else '✅ PASS'}")
    print(f"  Contains boilerplate: {'❌ FAIL' if has_boilerplate else '✅ PASS'}")
    
    return cleaned, stats

def test_full_normalization():
    """Test complete normalization pipeline"""
    print("\n" + "="*80)
    print("TEST 3: Full Normalization Pipeline")
    print("="*80)
    
    # Simulate dialogue sections like scraper would extract
    test_sections = [
        {'speaker': 'Donald Trump 00', 'text': 'Well, thank you very much. [Laughter]', 'timestamp': '00:00'},
        {'speaker': 'Mark Levin 00', 'text': 'Hold on. [Audience members call out "Amen"]', 'timestamp': '04:46'},
        {'speaker': 'Donald Trump (00:10:12)', 'text': 'Thank you for being here.', 'timestamp': ''},
    ]
    
    full_dialogue, speakers_json, word_count, trump_word_count, norm_stats = \
        normalize_transcript_format(test_sections)
    
    print(f"\nInput: {len(test_sections)} dialogue sections")
    print(f"Output word count: {word_count}")
    print(f"Trump word count: {trump_word_count}")
    print(f"Speakers: {speakers_json}")
    
    print(f"\nNormalization stats:")
    for key, value in norm_stats.items():
        print(f"  {key}: {value}")
    
    print(f"\nFull dialogue output:")
    print("-" * 80)
    print(full_dialogue)
    print("-" * 80)
    
    # Validation
    print(f"\nValidation:")
    speakers_list = json.loads(speakers_json)
    print(f"  Number of unique speakers: {len(speakers_list)}")
    print(f"  Speaker names: {speakers_list}")
    print(f"  Has '00' suffixes: {'❌ FAIL' if ' 00' in full_dialogue else '✅ PASS'}")
    print(f"  Has timestamps: {'❌ FAIL' if '00:' in full_dialogue else '✅ PASS'}")
    print(f"  Has annotations: {'❌ FAIL' if '[' in full_dialogue else '✅ PASS'}")
    print(f"  Has rating metadata: {'❌ FAIL' if 'SIGNAL' in full_dialogue or 'STRESS' in full_dialogue else '✅ PASS'}")

if __name__ == '__main__':
    print("\n" + "="*80)
    print("NORMALIZATION FUNCTION TEST SUITE")
    print("="*80)
    print("Testing against actual Dec 16 Hanukkah transcript data")
    print("="*80)
    
    test_speaker_normalization()
    cleaned, stats = test_artifact_stripping()
    test_full_normalization()
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)
    print("\nIf all validations show ✅ PASS, the normalization is working correctly.")
    print("Deploy to production and re-sync December 2025 transcripts.")
    print("="*80 + "\n")


