const COMMON_WORDS = new Set([
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
]);

function analyzeWordFrequency(text, options = {}) {
    const {
        minLength = 3,
        excludeCommon = true,
        caseSensitive = false,
        maxWords = 1000
    } = options;

    const words = text
        .toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(word => {
            if (word.length < minLength) return false;
            if (excludeCommon && COMMON_WORDS.has(word)) return false;
            return true;
        });

    const frequency = {};
    words.forEach(word => {
        const key = caseSensitive ? word : word.toLowerCase();
        frequency[key] = (frequency[key] || 0) + 1;
    });

    const sorted = Object.entries(frequency)
        .sort((a, b) => b[1] - a[1])
        .slice(0, maxWords);

    return Object.fromEntries(sorted);
}

function getTopWords(text, count = 20, excludeCommon = true) {
    const frequencies = analyzeWordFrequency(text, { excludeCommon });
    return Object.entries(frequencies)
        .slice(0, count)
        .map(([word, freq]) => ({ word, frequency: freq }));
}

function analyzeWordTrends(transcripts, word) {
    const trends = transcripts
        .filter(t => t.full_text && t.date)
        .map(transcript => {
            const text = transcript.full_text.toLowerCase();
            const words = text.split(/\s+/);
            const count = words.filter(w => w === word.toLowerCase()).length;

            return {
                date: transcript.date,
                count,
                speechType: transcript.speech_type,
                title: transcript.title
            };
        })
        .sort((a, b) => new Date(a.date) - new Date(b.date));

    return trends;
}

function compareWordFrequencies(transcripts1, transcripts2) {
    const text1 = transcripts1.map(t => t.full_text).join(' ');
    const text2 = transcripts2.map(t => t.full_text).join(' ');

    const freq1 = analyzeWordFrequency(text1);
    const freq2 = analyzeWordFrequency(text2);

    const allWords = new Set([...Object.keys(freq1), ...Object.keys(freq2)]);
    const comparison = [];

    allWords.forEach(word => {
        const count1 = freq1[word] || 0;
        const count2 = freq2[word] || 0;
        const difference = count2 - count1;

        comparison.push({
            word,
            group1Count: count1,
            group2Count: count2,
            difference,
            percentChange: count1 > 0 ? ((count2 - count1) / count1) * 100 : null
        });
    });

    return comparison.sort((a, b) => Math.abs(b.difference) - Math.abs(a.difference));
}

function extractPhrases(text, phraseLength = 2, minFrequency = 2) {
    const words = text
        .toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 2);

    const phrases = {};

    for (let i = 0; i <= words.length - phraseLength; i++) {
        const phrase = words.slice(i, i + phraseLength).join(' ');
        phrases[phrase] = (phrases[phrase] || 0) + 1;
    }

    return Object.entries(phrases)
        .filter(([_, freq]) => freq >= minFrequency)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 100)
        .map(([phrase, frequency]) => ({ phrase, frequency }));
}

module.exports = {
    analyzeWordFrequency,
    getTopWords,
    analyzeWordTrends,
    compareWordFrequencies,
    extractPhrases
};
