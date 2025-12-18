import re
from collections import Counter
from typing import Dict

COMMON_WORDS = {
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
    'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
    'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
    'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their',
    'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go',
    'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
    'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them',
    'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over',
    'think', 'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work',
    'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
    'give', 'day', 'most', 'us', 'is', 'was', 'are', 'been', 'has', 'had',
    'were', 'said', 'did', 'having', 'may', 'should', 'am', 'being'
}

def analyze_word_frequency(text: str, min_length: int = 3,
                          exclude_common: bool = True,
                          max_words: int = 500) -> Dict[str, int]:
    """
    Analyze word frequency in text

    Args:
        text: Input text to analyze
        min_length: Minimum word length to include
        exclude_common: Whether to exclude common words
        max_words: Maximum number of words to return

    Returns:
        Dictionary of word: frequency pairs
    """
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-z]+\b', text.lower())

    # Filter words
    filtered_words = []
    for word in words:
        if len(word) >= min_length:
            if not exclude_common or word not in COMMON_WORDS:
                filtered_words.append(word)

    # Count frequencies
    word_counts = Counter(filtered_words)

    # Return top N words
    return dict(word_counts.most_common(max_words))

def count_words(text: str) -> int:
    """Count total words in text"""
    words = re.findall(r'\b\w+\b', text)
    return len(words)
