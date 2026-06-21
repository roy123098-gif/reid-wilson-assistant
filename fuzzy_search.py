from difflib import SequenceMatcher
import re

SYNONYMS = {
    "nephew": ["qualifying child", "relationship test", "dependent"],
    "niece": ["qualifying child", "relationship test", "dependent"],
    "babysitter": ["child care", "dependent care", "work-related expenses"],
    "daycare": ["child care", "dependent care"],
    "side job": ["self-employment", "earned income"],
    "self employed": ["self-employment", "earned income"],
    "job": ["wages", "earned income"],
    "worked": ["wages", "earned income"],
    "lived with me": ["residency test", "more than half the year"],
    "stay with me": ["residency test"],
    "file taxes": ["filing requirement", "must file"],
    "refund": ["credit", "earned income credit"],
    "kid": ["child", "qualifying child"],
    "children": ["child", "qualifying child"],
    "single mom": ["head of household", "qualifying child", "earned income credit"],
    "single parent": ["head of household", "qualifying child", "earned income credit"],
    "student": ["earned income", "qualifying child", "education"],
    "ssn": ["social security number", "valid SSN"],
    "social security": ["social security number", "valid SSN"],
    "green card": ["resident alien", "valid SSN"],
    "married": ["filing status", "joint return"],
    "separated": ["filing status", "joint return"],
    "homeless": ["residency test", "temporary absence"],
    "disabled": ["permanently and totally disabled", "qualifying child"],
}

NOISY_TITLE_WORDS = ["contents", "index", "getting tax publications", "forms and publications"]


def semantic_similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def expand_query(query):
    query = query.lower()
    expanded = {query}
    for key, values in SYNONYMS.items():
        if key in query:
            expanded.update(values)
    return list(expanded)


def query_words(query):
    skip = {"the", "and", "for", "with", "that", "this", "what", "does", "can", "you", "are", "was", "did", "have"}
    return {word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", query.lower()) if word not in skip}


def matched_terms(sentence, title, summary, expanded_query, query):
    haystack = f"{sentence or ''} {title} {summary}".lower()
    matches = []
    for term in expanded_query:
        if term and term in haystack:
            matches.append(term)
    for word in query_words(query):
        if word in haystack:
            matches.append(word)
    return sorted(set(matches))


def score_text(text, expanded_query, weight=1):
    text_lower = text.lower()
    score = 0
    for term in expanded_query:
        if term in text_lower:
            score += 5 * weight
        sim = semantic_similarity(term, text_lower)
        if sim > 0.6:
            score += sim * 4 * weight
    return score


def score_sentence(sentence, expanded_query):
    return score_text(sentence, expanded_query, 1)


def noise_penalty(title, content):
    title_lower = title.lower()
    penalty = 0
    if any(word in title_lower for word in NOISY_TITLE_WORDS):
        penalty += 8
    if len(content) > 2500 and len(re.findall(r"\b\d{1,2}\b", content)) > 20:
        penalty += 5
    return penalty


def rank_sections(query, section_index):
    expanded = expand_query(query)
    section_scores = []
    for title, data in section_index.items():
        best_sentence = None
        best_score = 0
        for sentence in data["sentences"]:
            s = score_sentence(sentence, expanded)
            if s > best_score:
                best_score = s
                best_sentence = sentence

        title_score = score_text(title, expanded, 2.5)
        summary_score = score_text(data["summary"], expanded, 1.5)
        final_score = max(best_score, 0) + title_score + summary_score - noise_penalty(title, data["raw_text"])
        final_score = max(final_score, 0)

        section_scores.append({
            "title": title,
            "score": final_score,
            "best_sentence": best_sentence,
            "summary": data["summary"],
            "content": data["raw_text"],
            "matched_terms": matched_terms(best_sentence, title, data["summary"], expanded, query),
        })
    section_scores.sort(key=lambda x: x["score"], reverse=True)
    return section_scores
