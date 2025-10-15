"""
Gemini API integration for translations and definitions
"""

import re
import json
import time
from pathlib import Path
from typing import List, Dict, Optional


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


def create_prompt_for_batch(words_batch: List[Dict], language: str, 
                            context_sentences: bool = True) -> str:
    """
    Create optimized Gemini prompt for batch translation
    
    Args:
        words_batch: List of word dictionaries with 'word', 'usage', 'book', 'lemma'
        language: 'en' or 'de'
        context_sentences: Include usage examples
        
    Returns:
        Formatted prompt string (in German - optimized!)
    """
    prompt_intro = """Du bist ein Experte für Sprachenlernen und erstellst hochwertige Anki-Karteikarten.

WICHTIGE REGELN:
1. Verben IMMER im Infinitiv angeben
2. Kontextsatz: Die Zielvokabel im Satz mit <b>...</b> fett markieren

"""
    
    if language == 'en':
        prompt_intro += """
AUFGABE: Gib für jede Vokabel NUR zurück:
- EN_definition: LIES DEN KONTEXT! Gib BEIDE Bedeutungen an:
    1. Die Bedeutung die IM KONTEXT verwendet wird (ZUERST!)
    2. Falls es eine andere häufige Bedeutung gibt, auch diese (mit "also:")
    Beispiel: "breeding" im Kontext Person = "upbringing, good manners (also: animal reproduction)"
- DE_gloss: Deutsche Übersetzung die ZUM KONTEXT passt
    REGELN für DE_gloss:
    • Verben im INFINITIV (z.B. "wiegen" NICHT "wiegte")
    • Normale deutsche Rechtschreibung (Substantive beginnen mit Großbuchstaben)
    • Mehrere Bedeutungen mit Komma trennen (z.B. "rufen, anfunken, kontaktieren")
    • Breite Übersetzung bevorzugen (z.B. "Haufen" NICHT nur "Müllhaufen")
    • Bei Fachbegriffen korrekte deutsche Begriffe (z.B. "Kommandoturm" für "conning tower")
- Notes: Nur wenn WIRKLICH hilfreich! "" wenn nichts zutrifft.
    Erlaubt: 
    • Register (umgangsspr./formell)
    • Variante (BE/AE)
    • Falsche Freunde
    • Formen ZEIGEN (z.B. "go-went-gone" NICHT "irregular")
    • Wendungen
    • Tonalität (z.B. "negative connotation", "formal/literary", "admiring tone")
    • Fremdwort: ERKLÄRE das deutsche Fremdwort! (z.B. "Fremdwort 'heuristisch' = durch Probieren lernend")
      → Bei seltenen Latein/Griechisch-Wörtern (obeisance, supercilious, etc.) IMMER Fremdwort-Note!

⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen! Tonalität bei wertenden Wörtern!
⚠️ WICHTIG: Original_word, EN_lemma, Context_HTML und Book NICHT ausgeben - werden automatisch ergänzt!

"""
    else:  # de
        prompt_intro += """
AUFGABE: Gib für jede Vokabel NUR zurück:
- DE_definition: LIES DEN KONTEXT! Gib BEIDE Bedeutungen an (einfache Worte):
    1. Die Bedeutung die IM KONTEXT verwendet wird (ZUERST!)
    2. Falls es eine andere häufige Bedeutung gibt, auch diese (mit "auch:")
- Notes: Nur wenn WIRKLICH hilfreich! "" wenn nichts zutrifft.
    Erlaubt: 
    • Register (umgangsspr./formell/gehoben)
    • Variante (regional/Jugend)
    • Falsche Freunde
    • Fremdwort: ERKLÄRE das Fremdwort! (z.B. "Latinismus, bedeutet: ...")
    • Wendungen
    • Tonalität (z.B. "abwertend", "gehoben", "bewundernd")

⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen! Tonalität bei wertenden Wörtern!
⚠️ WICHTIG: Original_word, DE_lemma, Context_HTML und Book NICHT ausgeben - werden automatisch ergänzt!
"""
    
    # Vokabeln hinzufügen mit Lemmatisierung
    prompt_words = "VOKABELN:\n\n"
    for i, word_data in enumerate(words_batch, 1):
        word = word_data['word']
        lemma = word_data.get('lemma', word.lower())
        usage = word_data.get('usage', '')
        book = word_data.get('book', '')
        
        prompt_words += f"{i}. Wort: {word}\n"
        prompt_words += f"   Lemma: {lemma}\n"
        
        if usage:
            prompt_words += f"   Kontext: {usage}\n"
        
        if book and book != 'Unknown':
            prompt_words += f"   Buch: {book}\n"
        
        prompt_words += "\n"
    
    prompt_output = """
AUSGABEFORMAT: Gib ausschließlich ein gültiges JSON-Array zurück, ohne zusätzliche Erklärungen oder Markdown-Formatierung.
Jedes Objekt repräsentiert NUR die generierten Felder für eine Vokabel (in dieser Reihenfolge).

"""
    
    if language == 'en':
        prompt_output += """Beispiel (nur die 3 generierten Felder):
[
  {
    "EN_definition": "upbringing, good manners, and refinement (also: the mating and production of offspring by animals)",
    "DE_gloss": "vornehme Erziehung, gute Manieren",
    "Notes": ""
  },
  {
    "EN_definition": "to collect someone or something (also: to lift, to learn, to improve)",
    "DE_gloss": "abholen, aufsammeln",
    "Notes": "phrasal verb"
  },
  {
    "EN_definition": "to die",
    "DE_gloss": "den Löffel abgeben, sterben",
    "Notes": "idiomatic expression; informal"
  },
  {
    "EN_definition": "the official residence of the British Prime Minister (also: metonym for the UK government)",
    "DE_gloss": "Downing Street",
    "Notes": "proper noun; metonym for UK government"
  },
  {
    "EN_definition": "behaving as though one is superior to others",
    "DE_gloss": "überheblich, hochmütig",
    "Notes": "Fremdwort (lat. 'supercilium' = Augenbraue); formal/literary; negative connotation"
  }
]
"""
    else:
        prompt_output += """Beispiel (nur die 2 generierten Felder):
[
  {
    "DE_definition": "jemanden heftig kritisieren oder anprangern (auch: mit einer Geißel schlagen)",
    "Notes": "gehoben/literarisch"
  },
  {
    "DE_definition": "sterben",
    "Notes": "Redewendung; nicht wörtlich; umgangssprachlich"
  },
  {
    "DE_definition": "jemanden durch ständiges Nerven erschöpfen oder irritieren",
    "Notes": "umgangssprachlich; Partizip II von 'abnerven'"
  },
  {
    "DE_definition": "Amtssitz des US-Präsidenten (auch: Synonym für die US-Regierung)",
    "Notes": "Eigenname; Metonym für US-Regierung"
  }
]
"""
    
    return prompt_intro + prompt_words + prompt_output


def process_batch_with_gemini(words_batch: List[Dict], language: str, genai, 
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
    
    from .config import CONFIG
    
    prompt = create_prompt_for_batch(words_batch, language, context_sentences=True)
    
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
                for i, word_data in enumerate(words_batch):
                    if i < len(parsed_data):
                        gemini_result = parsed_data[i]
                        
                        # Create card with Context_HTML (highlighted or cloze)
                        usage_plain = word_data.get('usage', '')

                        # Always keep a bold version for EN→DE and DE→DE cards
                        context_html = make_context_html(usage_plain, word_data['word'], use_cloze=False)

                        # For DE→EN we need a cloze version, but only EN source words require it
                        context_cloze = None
                        if language == 'en':
                            context_cloze = make_context_html(usage_plain, word_data['word'], use_cloze=True)
                        
                        # Extract translation/definition
                        translation = gemini_result.get('DE_gloss', '') if language == 'en' else ''
                        definition = gemini_result.get('EN_definition', '') if language == 'en' else gemini_result.get('DE_definition', '')
                        
                        # Build card with language-specific schema in correct order
                        if language == 'en':
                            card = {
                                'EN_lemma': word_data.get('lemma', word_data['word'].lower()),
                                'Original_word': word_data['word'],
                                'EN_definition': definition,
                                'DE_gloss': translation,
                                'Context_HTML': context_html,
                                'Context_Cloze': context_cloze or '',
                                'Notes': gemini_result.get('Notes', ''),
                                'Book': word_data.get('book', 'Unknown')
                            }
                        else:  # de
                            card = {
                                'DE_lemma': word_data.get('lemma', word_data['word'].lower()),
                                'Original_word': word_data['word'],
                                'DE_definition': definition,
                                'Context_HTML': context_html,
                                'Notes': gemini_result.get('Notes', ''),
                                'Book': word_data.get('book', 'Unknown')
                            }
                        
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
