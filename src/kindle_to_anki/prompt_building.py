from kindle_to_anki.db_reader import WordRecord
from enum import Enum
from dataclasses import dataclass

class PromptType(Enum):
    NATIVE_DEFINITION = "native_definition"
    FOREIGN_VOCABULARY = "foreign_vocabulary"

@dataclass
class PromptJob:
    prompt: str
    type: PromptType
    words: list[WordRecord]
    response: str | None = None

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

def separate_words_by_language(words: list[WordRecord]) -> dict[str, list[WordRecord]]:
    """
    Separates words by language
    :param words:
        List of mixed-language WordRecord objects
    :return:
        Dictionary mapping each language code to a list of the corresponding WordRecord objects
    """
    separated_words = {}
    for word in words:
        if word.lang not in separated_words:
            separated_words[word.lang] = [word]
        else:
            separated_words[word.lang].append(word)
    return separated_words


def make_word_block(batch: list[WordRecord]) -> str:
    book_title_to_letter = {}

    # Map all book titles to a specific letter, starting from A
    unicode_integer = 65
    for word in batch:
        book_title = word.origin.title
        if book_title not in book_title_to_letter:
            book_title_to_letter[book_title] = chr(unicode_integer)
            unicode_integer += 1
    # Match Book title to key, e.g. LOTR : A
    block = ["\n".join([f"{k} : {v}" for k, v in book_title_to_letter.items()]), "VOCABULARY ITEMS:"]
    for i, word in enumerate(batch):
        book_title = word.origin.title
        block.append(f"""
ITEM { i + 1 }
word: {word.word}
context: {word.context}
book: {book_title_to_letter[book_title]}
                     """.strip())
    return "\n".join(block)


def get_batches(words_one_language: list[WordRecord], batch_size: int) -> list[list[WordRecord]]:
    """
    Splits the words provided into multiple batches of size batch_size
    :param words_one_language:
        List of words, which already have the same language
    :param batch_size:
        Integer, specifying how large each batch is
    :return:
        A list of multiple batches, each batch is a list of WordRecord objects.
    """
    if batch_size < 1:
        raise ValueError(f"Batch size:{batch_size} needs to be greater than zero")
    batches = []
    for start in range(0, len(words_one_language), batch_size):
        batches.append(words_one_language[start:start + batch_size])
    return batches


def get_all_prompts(separated_words_by_language: dict[str, list[WordRecord]], native_language_code: str, batch_size: int) -> dict[str, list[PromptJob]]:
    """
    Creates LLM prompts for all languages

    :param separated_words_by_language:
        Dictionary mapping language codes to the corresponding WordRecord objects
        Example: {"de": [word1, word2], "fr": [word3]}
    :param native_language_code:
        Language code of the users native language, e.g. "de" or "fr"
    :param batch_size:
        Maximum numbers of words to include in one LLM prompt

    :return:
        Dictionary mapping each language code to a list of PromptJob's containing, but not limited to:
            - the prompt itself
            - the WordRecord objects which were used making the prompt
    """
    prompts = {}
    # Build prompts by language
    for language_code in separated_words_by_language:
        batches = get_batches(separated_words_by_language[language_code], batch_size)
        for batch in batches:
        # Build prompts
            # Skip if batch is empty
            if len(batch) == 0:
                continue
            full_prompt = batch_to_prompt(batch, native_language_code, language_code)
            prompt_job = PromptJob(
                prompt=full_prompt,
                type=(PromptType.NATIVE_DEFINITION if language_code == native_language_code else PromptType.FOREIGN_VOCABULARY), words=batch
            )
            if language_code in prompts:
                prompts[language_code].append(prompt_job)
            else:
                prompts[language_code] = [prompt_job]
    return prompts

def batch_to_prompt(batch: list[WordRecord], native_language_code: str, batch_language_code: str) -> str:
    """
    Creates prompt for one batch
    :param batch:
        List of WordRecords, which have the same language.
    :param native_language_code:
        The native language code.
    :param batch_language_code:
        Language code of the current batch
    :return: string containing the prompt for this batch
    """
    shared_prompt = build_shared_prompt()
    specified_prompt = build_definition_prompt(batch_language_code, native_language_code) if native_language_code == batch_language_code else build_foreign_vocabulary_prompt(batch_language_code, native_language_code)
    word_prompt = make_word_block(batch)
    return shared_prompt + "\n\n" + specified_prompt + "\n\n" + word_prompt


def build_shared_prompt():
    prompt = """
You are a language learning expert creating high-quality Anki flashcard fields.

The input items may be grouped by source book for context only.

Each item contains:
- word: the vocabulary item to process
- context: the sentence or short passage where the word appears
- book label: short book label for context only

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
"""
    return prompt.strip()


def get_language(language_code: str) -> str:
    try:
        return languages[language_code]
    except KeyError as e:
        raise ValueError(f"Language code {language_code} not recognized") from e

def build_foreign_vocabulary_prompt(source_language_code:str, native_language_code:str) -> str:
    source_language = get_language(source_language_code)
    native_language = get_language(native_language_code)
    if source_language_code == native_language_code:
        raise ValueError("Source language and native language are not allowed to match")

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
10. If the response schema contains collocations, write them in the source language.
11. If the response schema contains notes, use them only for learner-relevant hints, such as nuance, register, usage restrictions, false friends, or missing one-to-one equivalence.
12. Use the normal marker for additional meanings in the definition language, e.g. "also:" in English or "auch:" in German.
"""
    return specified_prompt.strip()


def build_definition_prompt(source_language_code: str, native_language_code: str) -> str:
    source_language = get_language(source_language_code)
    native_language = get_language(native_language_code)
    if source_language_code != native_language_code:
        raise ValueError("Native and source languages must match")
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
8. If the response schema contains alternatives, use them for close synonyms or equivalent expressions in the source language.
9. If the response schema contains notes, use them only for definition-relevant hints, such as nuance, register, usage restrictions, or learner traps.
10. Use the normal marker for additional meanings in the native language, e.g. "auch:" in German.
    """
    return specified_prompt.strip()