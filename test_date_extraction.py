#!/usr/bin/env python3
"""
Test suite for extract_date_from_url() function
Tests various URL formats that Roll Call might use
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_utils import extract_date_from_url


def test_standard_month_format():
    """Test standard month-name format with dash separator"""
    test_cases = [
        ("https://rollcall.com/factbase/trump/transcript/donald-trump-speech-december-19-2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/press-conference-january-7-2025", "2025-01-07"),
        ("https://rollcall.com/factbase/trump/transcript/remarks-march-31-2024", "2024-03-31"),
        ("https://rollcall.com/factbase/trump/transcript/interview-november-1-2025", "2025-11-01"),
    ]
    
    print("\n" + "="*80)
    print("TEST: Standard month-name format (dash separator)")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: {url.split('/')[-1][:50]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_alternate_separators():
    """Test month-name format with alternate separators"""
    test_cases = [
        ("https://rollcall.com/factbase/trump/transcript/speech=december-19-2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/speech_december_19_2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/speech/december/19/2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/pennsylvania=december-9-2025", "2025-12-09"),
    ]
    
    print("\n" + "="*80)
    print("TEST: Alternate separators (=, _, /)")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: {url.split('/')[-1][:50]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_iso_format():
    """Test ISO date format (YYYY-MM-DD)"""
    test_cases = [
        ("https://rollcall.com/factbase/trump/transcript/speech-2025-12-19", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/remarks-2024-09-15", "2024-09-15"),
        ("https://rollcall.com/factbase/trump/transcript/interview=2025-01-01", "2025-01-01"),
        ("https://rollcall.com/factbase/trump/transcript/press/2025/12/31", "2025-12-31"),
    ]
    
    print("\n" + "="*80)
    print("TEST: ISO date format (YYYY-MM-DD)")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: {url.split('/')[-1][:50]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_query_string_format():
    """Test date in query string parameters"""
    test_cases = [
        ("https://rollcall.com/factbase/trump/transcript/speech?date=december-19-2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/remarks?d=2025-12-19", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/press&date=january-1-2025", "2025-01-01"),
        ("https://rollcall.com/factbase/trump/transcript/interview&d=2024-11-30", "2024-11-30"),
    ]
    
    print("\n" + "="*80)
    print("TEST: Query string date parameters")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: {url.split('?')[0].split('/')[-1][:30] + '?' + url.split('?')[1] if '?' in url else url.split('&')[-1]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_real_world_examples():
    """Test actual URLs from the project"""
    test_cases = [
        # From transcript_links.json
        ("https://rollcall.com/factbase/trump/transcript/donald-trump-speech-political-rally-mount-pocono-pennsylvania=december-9-2025", "2025-12-09"),
        ("https://rollcall.com/factbase/trump/transcript/donald-trump-press-gaggle-air-force-one-december-9-2025", "2025-12-09"),
        ("https://rollcall.com/factbase/trump/transcript/donald-trump-remarks-congressional-ball-december-11-2025", "2025-12-11"),
        # From missing_urls.txt
        ("https://rollcall.com/factbase/trump/transcript/donald-trump-speech-pennsylvania-political-rally-mount-pocono-december-9-2025", "2025-12-09"),
    ]
    
    print("\n" + "="*80)
    print("TEST: Real-world URLs from the project")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: ...{url[-70:]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_edge_cases():
    """Test edge cases and invalid inputs"""
    test_cases = [
        # No date in URL
        ("https://rollcall.com/factbase/trump/transcript/some-speech", None),
        # Invalid date
        ("https://rollcall.com/factbase/trump/transcript/speech-invalidmonth-99-2025", None),
        # Empty string
        ("", None),
        # Mixed case month names (should work)
        ("https://rollcall.com/factbase/trump/transcript/speech-DECEMBER-19-2025", "2025-12-19"),
        ("https://rollcall.com/factbase/trump/transcript/speech-December-19-2025", "2025-12-19"),
    ]
    
    print("\n" + "="*80)
    print("TEST: Edge cases and invalid inputs")
    print("="*80)
    
    passed = 0
    for url, expected in test_cases:
        result = extract_date_from_url(url)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        display_url = url if url else "(empty string)"
        print(f"{status}: {display_url[:60]}")
        if result != expected:
            print(f"  Expected: {expected}, Got: {result}")
        else:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def run_all_tests():
    """Run all test suites"""
    print("\n" + "="*80)
    print("DATE EXTRACTION TEST SUITE")
    print("="*80)
    
    results = {
        "Standard month format": test_standard_month_format(),
        "Alternate separators": test_alternate_separators(),
        "ISO format": test_iso_format(),
        "Query string format": test_query_string_format(),
        "Real-world examples": test_real_world_examples(),
        "Edge cases": test_edge_cases(),
    }
    
    print("\n" + "="*80)
    print("OVERALL RESULTS")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED")
    print("="*80 + "\n")
    
    return all_passed


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

