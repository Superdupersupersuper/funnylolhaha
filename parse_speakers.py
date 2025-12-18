#!/usr/bin/env python3
"""
Parse speakers from transcripts and update database with speaker information.
"""

import sqlite3
import json
import re

# Exhaustive speaker list
SPEAKERS = [
    "Donald Trump", "Keir Starmer", "Unidentified Speaker", "Emmanuel Macron",
    "Narendra Modi", "Shigeru Ishiba", "Benjamin Netanyahu", "Sean Duffy",
    "Pete Hegseth", "J.D. Vance", "Anne Fundner", "Mike Johnson",
    "Janet Mills", "Jim Pillen", "Richard Attias", "Rosanna Maietta",
    "Borge Brende", "Stephen Schwarzman", "Patrick Pouyanné", "Brian Moynihan",
    "Ana Botin", "Laura Ingraham", "Kamala Harris", "Tammy Nobles",
    "Jonathan Martinez", "Tom Cole", "Steve Eagar", "Elon Musk",
    "R. Lee Ermey", "Rachel Levine", "Matthew Modine", "Kylie Minogue",
    "Qveen Herby", "Marines", "Kid Rock", "Will Scharf",
    "Aide", "Paula White-Cain", "Alina Habba", "Pam Bondi",
    "Randy Fine", "Howard Lutnick", "Nicole Malliotakis", "Sergio Gor",
    "Charles Kushner", "James Blair", "David Perdue", "Leah Campos",
    "Michael Waltz", "John Arrigo", "Kevin Cabrera", "Tom Barrack",
    "Pete Hoekstra", "Ron Johnson", "Matt Whitaker", "George Glass",
    "Ken Howery", "Stacey Feinberg", "Nicole McGraw", "Brandon Judd",
    "Brian Burch", "Somers Farkas", "Joe Popolo", "Mike Huckabee",
    "Tilman Fertitta", "Warren Stephens", "Jimmy Patronis", "Alek Skarlatos",
    "Kimberly Guilfoyle", "Doug Burgum", "Brooke Rollins", "Kelly Loeffler",
    "Lee Zeldin", "Doug Collins", "Chris Wright", "Linda McMahon",
    "Robert F. Kennedy, Jr.", "Kristi Noem", "Marco Rubio", "Scott Bessent",
    "Euisun Chung", "Steve Scalise", "Jeff Landry", "David W. Allvin",
    "Dale R. White", "Mary Martin", "Chuck Robbins", "Gianni Infantino",
    "Kevin Hassett", "David Sacks", "Tom Emmer", "Cameron Winklevoss",
    "Tyler Winklevoss", "Sergey Nazarov", "Rodolphe Saadé", "Lindsey Halligan",
    "Maria Bartiromo", "C.C. Wei", "Scott Turner", "Ron DeSantis",
    "Tiger Woods", "Tim Scott", "Leo Terrell", "Phil Heath",
    "Neil Gorsuch", "Cheryl Hines", "Tulsi Gabbard", "Abraham Williams",
    "Steve Witkoff", "Marc Fogel", "Dave McCormick", "Mark Fogel",
    "Stephen Miller", "Clarence Thomas", "Nancy Mace", "Tim Burchett",
    "Ronny Jackson", "Payton McNabb", "Paul Maurice", "Sergei Bobrovsky",
    "Vinnie Viola", "Sam Reinhart", "Matthew Tkachuk", "Allyson Phillips",
    "Franklin Graham", "Melania Trump", "Karen Bass", "Brad Sherman",
    "Judy Chu", "Kathryn Barger", "Vince Fong", "Kevin Kiley",
    "Joel Pollak", "Jay Obernolte", "Young Kim", "George Whitesides",
    "Traci Park", "Tom McClintock", "Ed Ring", "Ric Grenell",
    "Michael Whatley", "Larry Ellison", "Masayoshi Son", "Sam Altman",
    "Amy Klobuchar", "John Thune", "Chuck Schumer", "Hakeem Jeffries",
    "Deb Fischer", "John Roberts", "Chris LaNeve", "Joe Biden",
    # Additional speakers found in transcripts
    "Karoline Leavitt", "Sarah Huckabee Sanders", "Peter Navarro", "Russell Vought",
    "Charlie Kirk", "Lara Trump", "Eric Trump", "Mike Pompeo",
    "Sean Hannity", "Nikki Haley", "Greg Abbott", "Brian Kemp",
    "Tom Homan", "Marty Makary", "Adam Boehler", "Bruce LeVell",
    "Bryson DeChambeau", "Chip Roy", "David Pecker", "Emil Bove",
    "Hope Hicks", "Jake Tapper", "Joshua Steinglass", "Juan Merchan",
    "Matthew Colangelo", "Mike Lindell", "Patty Morin",
    "Sean O'Brien", "Saudi Protocol Officer", "Tamim bin Hamad Al Thani",
    "Todd Blanche", "Tom Hauser", "Mark Rutte"
]

def parse_speakers_from_text(text):
    """
    Parse speakers from transcript text.
    Looks for patterns like "Speaker Name:" or speaker names in statistics.
    """
    found_speakers = set()

    for speaker in SPEAKERS:
        # Pattern 1: "Speaker Name:" format (dialogue)
        pattern1 = re.compile(rf'(?:^|\n)\s*{re.escape(speaker)}\s*:', re.MULTILINE | re.IGNORECASE)

        # Pattern 2: "Speaker Name said X sentences" (statistics)
        pattern2 = re.compile(rf'{re.escape(speaker)}\s+said\s+\d+\s+sentences', re.IGNORECASE)

        # Pattern 3: Just the name appearing in title or metadata
        pattern3 = re.compile(rf'\b{re.escape(speaker)}\b', re.IGNORECASE)

        # If any pattern matches, add the speaker
        if pattern1.search(text) or pattern2.search(text) or pattern3.search(text):
            found_speakers.add(speaker)

    return list(found_speakers)

def bold_speakers_in_text(text, speakers):
    """
    Bold speaker names in text when they appear in "Speaker:" format.
    """
    if not speakers:
        return text

    for speaker in speakers:
        # Bold speaker name when followed by colon
        pattern = re.compile(rf'((?:^|\n)\s*)({re.escape(speaker)})(\s*:)', re.MULTILINE | re.IGNORECASE)
        text = pattern.sub(r'\1<strong>\2</strong>\3', text)

    return text

def update_database():
    """
    Update all transcripts in database with speaker information.
    """
    conn = sqlite3.connect('data/transcripts.db')
    cursor = conn.cursor()

    # Add speakers column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE transcripts ADD COLUMN speakers TEXT")
        conn.commit()
        print("Added speakers column to database")
    except sqlite3.OperationalError:
        print("Speakers column already exists")

    # Get all transcripts with title for better parsing
    cursor.execute("SELECT id, title, full_text FROM transcripts WHERE full_text IS NOT NULL AND full_text != ''")
    transcripts = cursor.fetchall()

    print(f"Processing {len(transcripts)} transcripts...")

    updated = 0
    speaker_counts = {}

    for transcript_id, title, full_text in transcripts:
        # Parse from both title and full text
        combined_text = f"{title}\n{full_text}"
        speakers = parse_speakers_from_text(combined_text)

        if speakers:
            # Store as JSON array
            speakers_json = json.dumps(speakers)
            cursor.execute("UPDATE transcripts SET speakers = ? WHERE id = ?", (speakers_json, transcript_id))
            updated += 1

            # Track speaker frequency
            for speaker in speakers:
                speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1

        if updated % 100 == 0:
            print(f"Processed {updated} transcripts with speakers...")
            conn.commit()

    conn.commit()
    conn.close()

    print(f"\n✓ Updated {updated} transcripts with speaker information")
    print(f"\nTop speakers found:")
    for speaker, count in sorted(speaker_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {speaker}: {count} transcripts")

if __name__ == "__main__":
    update_database()
