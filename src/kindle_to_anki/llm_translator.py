from typing import Iterator
from kindle_to_anki.db_reader import WordRecord

languages = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "bn": "Bengali",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "th": "Thai",
}

def separate_words_by_language(words:list[WordRecord]) -> dict[str, list[WordRecord]]:
    separated_words = {}
    for word in words:
        if word.lang not in separated_words:
            separated_words[word.lang] = [word]
        else:
            separated_words[word.lang].append(word)
    return separated_words

def make_word_block(batch:list[WordRecord]) -> str:
    books = {}
    # Map all words to a specific book
    for word in batch:
        book_title = word.origin.title
        if book_title not in books:
            books[book_title] = [word]
        else:
            books[book_title].append(word)

    block = []
    for book, words in books.items():
        block.append(f"Book: {book}\n")
        for word in words:
            block.append(f"""
                        word: {word.word}
                        context: {word.context}
                         """).strip()
    return "\n".join(block)


def get_batches(separated_words:list[WordRecord], batch_size:int) -> Iterator[list[WordRecord]]:
    batches = []
    for start in range(0, len(separated_words), batch_size):
        batches.append(separated_words[start:start+batch_size])
    return batches

def build_shared_prompt():
    prompt = """
    You are a language learning expert creating high-quality Anki flashcard fields.
    
    The input items may be grouped by source book for context only.
    Do not reproduce book grouping, book titles, context text, language metadata, or other automatically processed metadata unless required by the response schema.
    
    Each item contains:
    - word: the vocabulary item to process
    - context: the sentence or short passage where the word appears
    
    General rules:
    1. Use the context as the primary source for meaning.
    2. The first meaning must always match the meaning used in the context.
    3. Take tone, register, domain, and idiomatic usage into account.
    4. Preserve the input order exactly across all vocabulary items.
    5. Return exactly one result for each input item.
    6. Include the normalized lemma/canonical form in the schema field intended for it. The lemma must be in the vocabulary/source language.
    7. If the context is insufficient, choose the most likely meaning and reflect uncertainty in ambiguity and confidence.
    8. Do not invent information that is not supported by the word and context.
    9. Use neutral dictionary forms suitable for flashcards:
       - verbs: infinitive
       - nouns: singular nominative / dictionary form where appropriate
       - adjectives: positive/base form
       - adverbs: base form
       - fixed expressions: canonical expression form
    10. For verbs, use the infinitive form whenever you output a vocabulary form, translation, alternative, or collocation.
    11. Keep outputs concise and suitable for Anki flashcards.
    12. Return only the structured output required by the response schema.
    
    Metadata rules:
    - notes: short learner-facing hint in the native language only if useful; otherwise empty
    - ambiguity: always one of low, medium, high
    - sense: contextual meaning, only when ambiguity is medium or high; otherwise empty
    - domain: field such as legal, medical, IT; leave empty for general language
    - alternatives: up to three meaningful alternatives
    - register: style such as colloquial, formal, literary; leave empty if neutral
    - false_friend: false or a short warning string
    - collocations: up to two typical collocations
    - anchor: shortest exact word or phrase copied from the context that identifies the relevant usage; usually one word, up to five words for idioms, phrasal verbs, or fixed expressions
    - confidence: number between 0 and 1
    """.strip()
    return prompt

def build_foreign_vocabulary_prompt(words:list[WordRecord], native_language_code:str) -> str:
    source_language = languages.get(words[0].lang, "Unknown language")
    native_language = languages.get(native_language_code, "Unknown language")
    if source_language == native_language:
        raise ValueError("Source language and native language are not allowed to match")
    shared_prompt = build_shared_prompt()
    specified_prompt = f"""
    YOUR TASK: Foreign Vocabulary Card Fields

    Vocabulary/source language:
    {source_language}

    Native/translation language:
    {native_language}

    This batch contains only vocabulary items whose source language is different from the native language.

    Generate the fields needed for a foreign-language Anki vocabulary card:
    - lemma/canonical form in the source language
    - concise definition or explanation in the source language, considering the context
    - context-fitting translation/gloss in the native language

    Task-specific rules:
    1. Generate the lemma/canonical form in the source language.
    2. Write the definition in the source language.
    3. Write the translation/gloss in the native language.
    4. The translation/gloss should translate the vocabulary item or expression, not the whole context.
    5. The translation/gloss should be short and natural enough to serve as an Anki cue or answer.
    6. The definition should explain the contextual meaning, not merely list synonyms.
    7. Prefer the contextual meaning over broad dictionary meanings in both the definition and the translation.
    8. If the item is a fixed expression, idiom, phrasal verb, or collocation, process the expression-level meaning.
    9. Follow the grammar, orthography, capitalization, punctuation, and word-formation conventions of the respective output language.
    10. If the response schema contains alternatives, use them for useful alternatives translations into the native language.
    11. If the response schema contains notes, use them only for learner-relevant hints, such as nuance, register, usage restrictions, false friends, or missing one-to-one equivalence.
    12. Use the normal marker for additional meanings in the definition language, e.g. "also:" in English or "auch:" in German.
    """.strip()

    return shared_prompt + "\n\n" + specified_prompt

def build_definition_prompt(words:list[WordRecord], native_language_code:str) -> str:
    try:
        native_language = languages[native_language_code]
        source_language = languages[words[0].lang]
    except KeyError:
        pass
        # UNKNOWN LANGUAGE
    except IndexError:
        # SKIP NO WORDS TO TRANSLATE
        pass
    if source_language != native_language:
        raise ValueError("Native and source languages do not match")
    shared_prompt = build_shared_prompt()
    specified_prompt = f"""
    YOUR TASK: Native Vocabulary Definition
    
    Vocabulary/source language:
    {source_language}
    
    Native language:
    {native_language}
    
    This batch contains only vocabulary items whose source language is the native language.
    
    Generate a concise definition or explanation in the native language.
    
    Task-specific rules:
    1. The definition must explain the contextual meaning of the vocabulary item.
    2. The definition must be written in the native language.
    3. Do not translate the vocabulary item into another language.
    4. The definition should explain the meaning, not merely list synonyms.
    5. If the item is a fixed expression, idiom, or collocation, define the expression-level meaning.
    6. Generate the lemma/canonical form in the native language.
    7. Follow the grammar, orthography, capitalization, punctuation, and word-formation conventions of the native language.
    8. If the response schema contains alternatives, use them for close synonyms or equivalent expressions in the native language.
    9. If the response schema contains notes, use them only for definition-relevant hints, such as nuance, register, usage restrictions, or learner traps.
    10. Use the normal marker for additional meanings in the native language, e.g. "auch:" in German.
    """.strip()
    return shared_prompt + "\n\n" + specified_prompt
