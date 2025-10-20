"""
Gemini API integration for translations and definitions
"""

import re
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import CONFIG
from .helpers import build_field_key, get_language_meta


def make_context_html(usage: str, original_word: str, use_cloze: bool = False) -> str:
    """
    Convert plain usage text to HTML with bold highlighting or cloze deletion
    
    Args:
        usage: Context sentence
        original_word: Word to highlight/hide (first occurrence)
        use_cloze: If True, use {{c1::word}} cloze deletion; if False, use <b>word</b>
        
    Returns:
        HTML string with <b>word</b> or {{c1::word}} format
    """
    if not usage or not original_word:
        return usage or ""
    
    # Escape special regex characters
    escaped_word = re.escape(original_word)
    
    # Match word boundary (case-insensitive, first occurrence only)
    pattern = re.compile(rf'\b({escaped_word})\b', re.IGNORECASE)
    
    # Replace first occurrence
    if use_cloze:
        # Cloze deletion for DE→EN cards (word is hidden)
        result = pattern.sub(r'{{c1::\1}}', usage, count=1)
    else:
        # Bold for EN→DE and DE→DE cards (word is visible)
        result = pattern.sub(r'<b>\1</b>', usage, count=1)
    
    return result


def setup_gemini_api(api_key: str, verbose: bool = False):
    """
    Initialize Gemini API
    
    Args:
        api_key: Gemini API key
        verbose: Enable verbose output
        
    Returns:
        genai module or None
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        if verbose:
            print("✅ Gemini API configured successfully")
        
        return genai
    
    except Exception as e:
        if verbose:
            print(f"❌ Gemini API setup failed: {e}")
        return None


def create_prompt_for_batch(words_batch: List[Dict], word_language: str,
                            native_language: str, target_language: str,
                            context_sentences: bool = True) -> str:
    """Create an optimized (German) Gemini prompt for multilingual batches."""

    native_meta = get_language_meta(native_language)
    target_meta = get_language_meta(target_language)
    word_meta = get_language_meta(word_language)

    lemma_field = build_field_key(word_language, 'lemma')
    definition_field = build_field_key(word_language, 'definition')
    gloss_field = build_field_key(native_language, 'gloss')

    prompt_lines = [
        "Du bist ein Experte für Sprachenlernen und erstellst hochwertige Anki-Karteikarten.",
        "",
        "SPRACHEN:",
        f"- Native Language (Definitionen & Notes): {native_meta['german_name']} ({native_language.upper()})",
        f"- Zielvokabel-Sprache: {target_meta['german_name']} ({target_language.upper()})",
        "",
        "WICHTIGE REGELN:",
        "1. Verben IMMER im Infinitiv angeben",
        "2. Kontextsatz: Die Zielvokabel im Satz mit <b>...</b> fett markieren",
        ""
    ]

    if word_language == target_language:
        prompt_lines.extend([
            "AUFGABE: Gib für jede Vokabel NUR zurück:",
            f"- {definition_field}: {target_meta['german_name']}e Definition (erst die im Kontext verwendete Bedeutung, danach "
            "optionale weitere häufige Bedeutung mit 'also:').",
            f"- {gloss_field}: {native_meta['german_name']}e Übersetzung, die zum Kontext passt (Verben im Infinitiv, Nomen groß, mehrere Bedeutungen mit Komma).",
            f"- Notes: Nur wenn WIRKLICH hilfreich. Schreibe die Notes in {native_meta['german_name']} (Register, Varianten, Falsche Freunde, Formen, Tonalität, Fremdwörter erklären).",
            "",
            "⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen, Tonalität berücksichtigen.",
            f"⚠️ WICHTIG: Original_word, {lemma_field}, Context_HTML und Book NICHT ausgeben – das übernimmt der Code automatisch.",
            ""
        ])
    else:
        prompt_lines.extend([
            "AUFGABE: Gib für jede Vokabel NUR zurück:",
            f"- {definition_field}: {native_meta['german_name']}e Definition in einfachen Worten (erst Kontext-Bedeutung, danach optionale häufige Bedeutung mit 'auch:').",
            f"- Notes: Nur wenn hilfreich. Schreibe Notes in {native_meta['german_name']} (Register, Varianten, Falsche Freunde, Fremdwörter erklären, Tonalität).",
            "",
            "⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen, Tonalität berücksichtigen.",
            f"⚠️ WICHTIG: Original_word, {lemma_field}, Context_HTML und Book NICHT ausgeben – das übernimmt der Code automatisch.",
            ""
        ])

    # Add Vocabs with lemmatization
    prompt_words = ["VOKABELN:\n"]
    for i, word_data in enumerate(words_batch, 1):
        word = word_data['word']
        lemma = word_data.get('lemma', word.lower())
        usage = word_data.get('usage', '')
        book = word_data.get('book', '')

        prompt_words.append(f"{i}. Wort: {word}\n")
        prompt_words.append(f"   Lemma: {lemma}\n")

        if context_sentences and usage:
            prompt_words.append(f"   Kontext: {usage}\n")

        if book and book != 'Unknown':
            prompt_words.append(f"   Buch: {book}\n")

        prompt_words.append("\n")

    prompt_output = [
        "AUSGABEFORMAT: Gib ausschließlich ein gültiges JSON-Array zurück – ohne Erklärungen oder Markdown.",
        "Jedes Objekt umfasst NUR die generierten Felder in exakt dieser Schreibweise.",
        "",
        "Beispiel:" 
    ]

    if word_language == target_language:
        prompt_output.append(
            f"\n[\n  {{\n    \"{definition_field}\": \"Definition Beispiel\",\n    \"{gloss_field}\": \"Übersetzung Beispiel\",\n    \"Notes\": \"optional in {native_meta['german_name']}\"\n  }},\n  {{\n    \"{definition_field}\": \"weitere Bedeutung (also: ... )\",\n    \"{gloss_field}\": \"alternative Übersetzung\",\n    \"Notes\": \"\"\n  }}\n]\n"
        )
    else:
        prompt_output.append(
            f"\n[\n  {{\n    \"{definition_field}\": \"Definition Beispiel\",\n    \"Notes\": \"Register-Hinweis in {native_meta['german_name']}\"\n  }},\n  {{\n    \"{definition_field}\": \"weitere Bedeutung (auch: ... )\",\n    \"Notes\": \"\"\n  }}\n]\n"
        )

    return "\n".join(prompt_lines) + "".join(prompt_words) + "\n".join(prompt_output)


def process_batch_with_gemini(words_batch: List[Dict], language: str,
                              native_language: str, target_language: str, genai,
                              verbose: bool = False, max_retries: int = 2,
                              batch_num: int = 0) -> List[Dict]:
    """
    Send batch to Gemini and parse JSON response
    
    Args:
        words_batch: List of word dictionaries
        language: 'en' or 'de'
        genai: Gemini API instance
        verbose: Enable verbose output
        max_retries: Maximum retry attempts
        batch_num: Batch number for logging
        
    Returns:
        List of processed cards or empty list on error
    """
    if not genai:
        return []
    
    prompt = create_prompt_for_batch(
        words_batch,
        word_language=language,
        native_language=native_language,
        target_language=target_language,
        context_sentences=True,
    )
    
    # Save raw input (prompt) if configured
    if CONFIG.get('SAVE_RAW_INPUTS'):
        try:
            output_dir = Path('anki_cards/raw_inputs')
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            input_file = output_dir / f"prompt_{language}_batch{batch_num}_{timestamp}.txt"
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
        except Exception as e:
            if verbose:
                print(f"    ⚠️  Could not save raw input: {e}")
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Token counting (verbose)
        if verbose:
            input_tokens = len(prompt.split())
            print(f" (in: ~{input_tokens})", end="", flush=True)
        
        # Try with retries
        for attempt in range(max_retries + 1):
            try:
                response = model.generate_content(prompt)
                response_text = response.text.strip()
                
                # Token counting (verbose)
                if verbose:
                    output_tokens = len(response_text.split())
                    total_tokens = input_tokens + output_tokens
                    print(f" (out: ~{output_tokens}) (total: ~{total_tokens})", end="", flush=True)
                
                # Save raw response if configured
                if CONFIG.get('SAVE_RAW_RESPONSES'):
                    try:
                        output_dir = Path('anki_cards/raw_responses')
                        output_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = time.strftime('%Y%m%d_%H%M%S')
                        response_file = output_dir / f"response_{language}_batch{batch_num}_{timestamp}.txt"
                        with open(response_file, 'w', encoding='utf-8') as f:
                            f.write(response_text)
                    except Exception as e:
                        if verbose:
                            print(f"    ⚠️  Could not save raw response: {e}")
                
                # Extract JSON (handle markdown code blocks)
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0].strip()
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0].strip()
                
                # Parse JSON
                parsed_data = json.loads(response_text)
                
                # Validate structure
                if not isinstance(parsed_data, list):
                    raise ValueError("Response is not a JSON array")
                
                # Match responses with input words
                results = []
                lemma_key = build_field_key(language, 'lemma')
                definition_key = build_field_key(language, 'definition')
                gloss_key = build_field_key(native_language, 'gloss')
                for i, word_data in enumerate(words_batch):
                    if i < len(parsed_data):
                        gemini_result = parsed_data[i]
                        
                        # Create card with Context_HTML (highlighted or cloze)
                        usage_plain = word_data.get('usage', '')

                        # Create context with <b>word</b> highlighting
                        # export.py will convert to {{c1::word}} for cloze cards on-the-fly
                        context_html = make_context_html(usage_plain, word_data['word'], use_cloze=False)
                        
                        # Extract translation/definition
                        definition = gemini_result.get(definition_key, '') or ''
                        notes_value = gemini_result.get('Notes', '') or ''
                        translation = ''
                        if language == target_language:
                            translation = gemini_result.get(gloss_key, '') or ''
                        
                        # Build card with language-specific schema in correct order
                        card = {
                            lemma_key: word_data.get('lemma', word_data['word'].lower()),
                            'Original_word': word_data['word'],
                            definition_key: definition,
                            'Context_HTML': context_html,
                            'Notes': notes_value,
                            'Book': word_data.get('book', 'Unknown'),
                        }

                        if language == target_language:
                            card[gloss_key] = translation
                        
                        results.append(card)
                    else:
                        # Gemini returned fewer results than expected
                        if verbose:
                            print(f"    ⚠️  Missing result for word #{i+1}: {word_data['word']}")
                
                if verbose and results:
                    print(f"✅ {len(results)} cards")
                
                return results
            
            except json.JSONDecodeError as e:
                if attempt < max_retries:
                    if verbose:
                        print(f"⚠️  JSON error (retry {attempt + 1}/{max_retries + 1})")
                    continue
                else:
                    if verbose:
                        print(f"❌ JSON parse failed after {max_retries + 1} attempts")
                    return []
            
            except Exception as e:
                if attempt < max_retries:
                    if verbose:
                        print(f"⚠️  API error (retry {attempt + 1}/{max_retries + 1}): {str(e)[:50]}")
                    continue
                else:
                    if verbose:
                        print(f"❌ API failed: {str(e)[:50]}")
                    return []
    
    except Exception as e:
        if verbose:
            print(f"❌ Batch processing failed: {e}")
        return []
