#!/usr/bin/env python3
"""
Test the new RollCall-specific parser in scraper_utils.py
"""

import sys
sys.path.insert(0, '/Users/alexandermiron/Downloads/mention-markets')

# Create mock driver for testing
class MockDriver:
    pass

from scraper_utils import DialogueExtractor

# Sample raw RollCall text with all the metadata
SAMPLE_ROLLCALL_TEXT = """Donald Trump Attends a Hanukkah Reception - December 16, 2025 StressLens 3 Topics 8 Entities Moderation 7 Speakers Full Transcript:

Donald Trump 00
00:00-00:00:10 (10 sec)

NO STRESSLENS:
Well, thank you very much. Nice place. [Audience members call out "We love you"]

Donald Trump 00
00:10-00:00:50 (40 sec)

NO SIGNAL (0.125):
You like it a lot better with Trump than you like it with Biden. That's because you're smart.

Mark Levin 00
04:46-00:04:50 (4 sec)

NO STRESSLENS:
Hold on. And he loves Israel too.

Miriam Adelson 00
11:06-00:11:34 (28 sec)

NO SIGNAL (0):
Well, Mr. President, I stood for a second, but it was so painful. [Laughter]"""

def test_parser():
    """Test the RollCall parser"""
    print("\n" + "="*80)
    print("SCRAPER PARSER TEST")
    print("="*80)
    
    # Create extractor
    driver = MockDriver()
    extractor = DialogueExtractor(driver)
    
    # Parse the text
    dialogue_sections = extractor._parse_speaker_sections(SAMPLE_ROLLCALL_TEXT)
    
    print(f"\nExtracted {len(dialogue_sections)} dialogue sections")
    print("=" * 80)
    
    for i, section in enumerate(dialogue_sections, 1):
        speaker = section['speaker']
        text = section['text']
        print(f"\nSection {i}:")
        print(f"  Speaker: '{speaker}'")
        print(f"  Text: '{text[:100]}{'...' if len(text) > 100 else ''}'")
        print(f"  Length: {len(text)} chars")
        
        # Validation checks
        has_numeric_suffix = bool(' 00' in speaker or speaker.endswith('00'))
        has_ratings = any(x in text for x in ['NO SIGNAL', 'NO STRESSLENS', 'MEDIUM', 'WEAK'])
        has_timestamps = bool(':' in speaker and any(c.isdigit() for c in speaker.split(':')[0][-3:]))
        
        print(f"  ✓ Clean speaker name (no '00'): {'❌ FAIL' if has_numeric_suffix else '✅ PASS'}")
        print(f"  ✓ No rating metadata: {'❌ FAIL' if has_ratings else '✅ PASS'}")
        print(f"  ✓ No timestamp in speaker: {'❌ FAIL' if has_timestamps else '✅ PASS'}")
    
    print("\n" + "="*80)
    print("OVERALL VALIDATION")
    print("="*80)
    
    all_speakers = [s['speaker'] for s in dialogue_sections]
    all_text = ' '.join([s['text'] for s in dialogue_sections])
    
    print(f"Speakers found: {len(all_speakers)}")
    print(f"Unique speakers: {len(set(all_speakers))}")
    print(f"Speaker names: {set(all_speakers)}")
    print(f"Total dialogue length: {len(all_text)} chars")
    
    # Final checks
    has_any_00 = any(' 00' in s for s in all_speakers)
    has_any_ratings = any(x in all_text for x in ['NO SIGNAL', 'NO STRESSLENS', 'MEDIUM', 'WEAK'])
    has_any_timestamps_in_names = any('00:' in s for s in all_speakers)
    
    print(f"\nFinal Validation:")
    print(f"  All speakers clean (no '00'): {'❌ FAIL' if has_any_00 else '✅ PASS'}")
    print(f"  All text clean (no ratings): {'❌ FAIL' if has_any_ratings else '✅ PASS'}")
    print(f"  All speakers clean (no timestamps): {'❌ FAIL' if has_any_timestamps_in_names else '✅ PASS'}")
    
    if not has_any_00 and not has_any_ratings and not has_any_timestamps_in_names:
        print(f"\n🎉 ALL TESTS PASSED - Parser is working correctly!")
        return True
    else:
        print(f"\n⚠️  TESTS FAILED - Parser needs fixes")
        return False

if __name__ == '__main__':
    test_parser()


