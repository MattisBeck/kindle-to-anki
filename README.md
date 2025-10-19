 If this project helps you, **please give it a ⭐ on GitHub** — it really boosts visibility and momentum.

[![GitHub Stars](https://img.shields.io/github/stars/MattisBeck/kindle-to-anki?style=social)](https://github.com/MattisBeck/kindle-to-anki/stargazers)


# Kindle to Anki Converter

A simple python script which converts your Kindle's vocab.db files to context based flashcards via Gemini (you can get a free api key, these limits are enough).
Great for learning a new language and even improving your own!

## 🎯 Features

- **Automatic Lemmatization** with spaCy
- **AI-Generated Definitions** via Gemini 2.0 Flash
- **Multilingual card types (3 formats)** – L2→L1 (translation), L1→L2 (translation, cloze), L1→L1 (definition)
- **Direct APKG Export** with custom card design
- **Smart Caching** - only new vocabulary is translated; so you don't need to start all over again
- **Token-Optimized** (~75 tokens per word)
- **Night Mode Support**
- **Responsive Design** - so you can learn on all your devices

## 📖 Quick Start

1. **Clone Repository & Create Virtual Environment**:
   ```bash
   git clone https://github.com/MattisBeck/kindle-to-anki.git
   cd kindle-to-anki
   
   # Create virtual environment
   python3 -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # .venv\Scripts\activate   # Windows
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   > 💡 **Note**: The script will automatically tell you which spaCy language models you need to install based on your configured languages. Just run the script first, and it will guide you!

3. **Get your free Gemini API Key**:
   - Go to https://aistudio.google.com/apikey
   - Create your free API Key

4. **Add your Gemini API Key** in `kindle_to_anki/config.py`:
   ```python
   CONFIG = {
       'GEMINI_API_KEY': 'YOUR-API-KEY-HERE',
       'SOURCE_LANGUAGE': 'de',  # Your native language
       'TARGET_LANGUAGE': 'en',  # Language you're learning
       ...
   }
   ```

5. **Copy Kindle Database**:
   - Copy `vocab.db` from your Kindle to `put_vocab_db_here/` folder

6. **Run the Script**:
   ```bash
   python kindle-to-anki.py
   ```

7. **Import into Anki**:
   - Open Anki → File → Import
   - Select `anki_cards/apkg_files/anki_*.apkg`

## 🏗️ Project Structure

```
Kindle-to-Anki/
├── CHANGELOG.md               # Release history snapshot (in the future)
├── README.md                  # Setup guide and bilingual documentation
├── requirements.txt           # Minimal dependency list for pip install
├── kindle-to-anki.py          # Thin wrapper that calls the package entry point
├── tsv_to_apkg.py             # Converts TSV exports into APKG decks
├── kindle_to_anki/            # Modular application code that powers the CLI
│   ├── __init__.py            # Package metadata (version etc.)
│   ├── cache.py               # Translation cache loader/saver utilities
│   ├── config.py              # Central runtime configuration flags
│   ├── database.py            # Kindle vocab.db access helpers
│   ├── export.py              # TSV/APKG writers and validation helpers
│   ├── gemini_api.py          # Prompting logic for Gemini 2.0 Flash
│   ├── main.py                # Orchestrates the ETL pipeline
│   ├── normalization.py       # Lemmatization and text cleanup utilities
│   └── utils.py               # Logging, progress, and misc helpers
├── anki_cards/                # Generated artifacts and logs
│   ├── apkg_files/            # Ready-to-import Anki decks
│   ├── tsv_files/             # Raw TSV exports per card type
│   └── errors.log             # Latest run issues (if any)
└── put_vocab_db_here/         # Drop your Kindle vocab.db before running
```

## ⚙️ Configuration

Edit `kindle_to_anki/config.py` to customize:

```python
CONFIG = {
    # API & Paths
    'GEMINI_API_KEY': 'your-api-key',
    'VOCAB_DB_PATH': 'put_vocab_db_here/vocab.db',
    'TSV_OUTPUT_DIR': 'anki_cards/tsv_files',
    'APKG_OUTPUT_DIR': 'anki_cards/apkg_files',
    
    # Batch Settings (for current free API rate limits: 15 RPM, 1M TPM, 200 RPD)
    'BATCH_SIZE': 20,
    'DELAY_BETWEEN_BATCHES': 4.5,  # seconds
    
    # Output Options
    'CREATE_EN_DE_CARDS': True,     # English → German
    'CREATE_DE_EN_CARDS': True,     # German → English
    'CREATE_DE_DE_CARDS': True,     # German → German
    'CREATE_APKG': True,            # Auto-create APKG packages
    
    # Debugging
    'VERBOSE': False,               # Show detailed progress
    'SAVE_RAW_RESPONSES': False,    # Save Gemini responses (debug)
    'SAVE_RAW_INPUTS': False,       # Save prompts (debug)
}
```

## 🎨 Card Design

### EN→DE Cards (Blue Theme)
- **Front**: English word + context
- **Back**: German translation + definition + notes

### DE→EN Cards (Red Theme) - with Cloze
- **Front**: German translation + context (with hidden original word)
- **Back**: English word + definition + notes

### DE→DE Cards (Turquoise Theme)
- **Front**: German word + context
- **Back**: German definition + notes

**All cards include:**
- 📚 Source book
- 📝 Context sentence (word highlighted or hidden)
- 💡 Linguistic notes (register, phrasal verbs, idioms, etc.)
- 🌙 Night mode support
- 📱 Responsive design

## 🔄 Workflow

```mermaid
graph LR
    A[Kindle vocab.db] --> B[spaCy Lemmatization]
    B --> C[Gemini API]
    C --> D[Minimal JSON]
    D --> E[Python Reconstruction]
    E --> F[TSV Files]
    F --> G[genanki]
    G --> H[APKG Packages]
    H --> I[Anki Import]
```

**Token Optimization:**
- Gemini generates only: `EN_definition`, `DE_gloss`, `Notes`
- Python adds: `Original_word`, `Lemma`, `Context_HTML`, `Book`
- **Savings**: ~59% fewer output tokens

## 🌍 Supported Languages

The converter currently supports the following languages:

| Language | Code | spaCy Model | Status |
|----------|------|-------------|--------|
| 🇩🇪 German (Deutsch) | `de` | `de_core_news_sm` | ✅ Full support |
| 🇬🇧 English | `en` | `en_core_web_sm` | ✅ Full support |
| 🇪🇸 Spanish (Español) | `es` | `es_core_news_sm` | ✅ Full support |
| 🇫🇷 French (Français) | `fr` | `fr_core_news_sm` | ✅ Full support |
| 🇵🇱 Polish (Polski) | `pl` | `pl_core_news_sm` | ✅ Full support |

**Configure your language pair** in `kindle_to_anki/config.py`:
```python
CONFIG = {
    'SOURCE_LANGUAGE': 'de',  # Your native language (cards & prompts)
    'TARGET_LANGUAGE': 'en',  # Language you're learning (Kindle book)
    ...
}
```

> 💡 **The script will automatically detect which spaCy models you need!** When you run the script, it will tell you exactly which models to install if they're missing.

**Missing your language?** [Open an issue on GitHub](https://github.com/MattisBeck/kindle-to-anki/issues) and request support for your language!

## 📊 Example Output

**Sample run (360 EN + 528 DE words):**
```
✅ TSV created: anki_en_de.tsv (360 cards)
✅ TSV created: anki_de_en.tsv (360 cards)
✅ TSV created: anki_de_de.tsv (528 cards)

✅ APKG created: anki_en_de.apkg (360 cards)
✅ APKG created: anki_de_en.apkg (360 cards)
✅ APKG created: anki_de_de.apkg (528 cards)
```

## 🛠️ Troubleshooting

### spaCy Models Missing
The script will tell you which models you need. Simply run the command it suggests, for example:
```bash
python -m spacy download de_core_news_sm
python -m spacy download en_core_web_sm
```

### Gemini API Quota Exceeded
- Free tier: 15 RPM, 1,000,000 TPM, 200 RPD
- Adjust: `BATCH_SIZE` (smaller) and `DELAY_BETWEEN_BATCHES` (longer)

### APKG Generation Failed
```bash
pip install genanki
```

## 💡 Tips

1. **Use Cache**: On subsequent runs, only new vocabulary is translated
2. **Adjust Batch Size**: Smaller batches = better quality, slower processing
3. **Enable VERBOSE**: Set `VERBOSE=True` for detailed debugging output
4. **Manual TSV Editing**: Edit TSV files in Excel or Numbers before APKG creation, you can run the converter separately:
   ```bash
   python tsv_to_apkg.py
   ```
5. **Book Title Normalization**: Titles are automatically normalized for consistency

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

MIT License - Free for private and commercial use.

## 🙏 Credits
- **Anki** - thank you, without you, I wouldn't be so good at school
- **GitHub Student Devloper Pack** - without GitHub Copilot, I couldn't have done this project
- **Gemini 2.0 Flash** (Google) - AI-generated definitions
- **spaCy** - Automatic lemmatization
- **genanki** - APKG package generation
---

Have Fun! 🎉

---
> Gefällt dir das Projekt? **Gib ihm ein ⭐️ auf GitHub** – das hilft Sichtbarkeit & Weiterentwicklung enorm.

[![GitHub Stars](https://img.shields.io/github/stars/MattisBeck/kindle-to-anki?style=social)](https://github.com/MattisBeck/kindle-to-anki/stargazers)

# Kindle to Anki Converter (Deutsch)

Ein einfaches Python-Skript, das deine Kindle-vocab.db in kontextbasierte Karteikarten via Gemini umwandelt (kostenloser API-Key verfügbar, Limits meiner Meinung nach aus).
Perfekt zum Erlernen einer neuen Sprache und sogar zur Verbesserung deiner eigenen!

## 🎯 Funktionen

- **Automatische Lemmatisierung** mit spaCy
- **KI-generierte Definitionen** via Gemini 2.0 Flash
- **Mehrsprachige Kartentypen (3 Formate)** – L2→L1 (Übersetzung), L1→L2 (Übersetzung, Cloze), L1→L1 (Definition)
- **Direkter APKG-Export** mit eigenem Kartendesign
- **Intelligentes Caching** - nur neue Vokabeln werden übersetzt; du musst nicht von vorne anfangen
- **Token-optimiert** (ca. 75 Tokens pro Wort)
- **Night Mode Support**
- **Responsive Design** - lerne auf allen deinen Geräten

## 📖 Schnellstart

1. **Repository klonen & Virtual Environment erstellen**:
   ```bash
   git clone https://github.com/MattisBeck/kindle-to-anki.git
   cd kindle-to-anki
   
   # Virtual Environment erstellen
   python3 -m venv .venv
   source .venv/bin/activate  # macOS/Linux
   # .venv\Scripts\activate   # Windows
   ```

2. **Abhängigkeiten installieren**:
   ```bash
   pip install -r requirements.txt
   ```
   
   > 💡 **Hinweis**: Das Skript sagt dir automatisch, welche spaCy-Sprachmodelle du installieren musst, basierend auf deinen konfigurierten Sprachen. Führe einfach das Skript aus, es wird dich anleiten!

3. **Kostenlosen Gemini API Key holen**:
   - Gehe zu https://aistudio.google.com/apikey
   - Erstelle deinen kostenlosen API Key

4. **API Key eintragen** in `kindle_to_anki/config.py`:
   ```python
   CONFIG = {
       'GEMINI_API_KEY': 'DEIN-API-KEY-HIER',
       'SOURCE_LANGUAGE': 'de',  # Deine Muttersprache
       'TARGET_LANGUAGE': 'en',  # Sprache, die du lernst
       ...
   }
   ```

5. **Kindle-Datenbank kopieren**:
   - Kopiere `vocab.db` von deinem Kindle in den Ordner `put_vocab_db_here/`

6. **Skript ausführen**:
   ```bash
   python kindle-to-anki.py
   ```

7. **In Anki importieren**:
   - Öffne Anki → Datei → Importieren
   - Wähle `anki_cards/apkg_files/anki_*.apkg`

## 🏗️ Projektstruktur

```
Kindle-to-Anki/
├── CHANGELOG.md               # Versionshistorie und wichtige Änderungen (in der Zukunft)
├── README.md                  # Diese zweisprachige Anleitung
├── requirements.txt           # Abhängigkeitsliste für pip install
├── kindle-to-anki.py          # Schlanke Hülle, ruft den Paket-Einstieg auf
├── tsv_to_apkg.py             # Wandelt TSV-Exporte in APKG-Decks um
├── kindle_to_anki/            # Modulare Anwendung, die das CLI antreibt
│   ├── __init__.py            # Paket-Metadaten (Version usw.)
│   ├── cache.py               # Lade-/Speicherfunktionen für den Übersetzungs-Cache
│   ├── config.py              # Zentrale Laufzeitkonfiguration
│   ├── database.py            # Zugriffshilfen auf die Kindle vocab.db
│   ├── export.py              # TSV/APKG-Exporter und Validierungen
│   ├── gemini_api.py          # Prompt-Logik für Gemini 2.0 Flash
│   ├── main.py                # Orchestriert die ETL-Pipeline
│   ├── normalization.py       # Lemmatisierungs- und Textbereinigungstools
│   └── utils.py               # Logging, Fortschritt und weitere Helfer
├── anki_cards/                # Generierte Artefakte und Logs
│   ├── apkg_files/            # Fertige Anki-Decks zum Import
│   ├── tsv_files/             # Rohe TSV-Ausgaben pro Kartentyp
│   └── errors.log             # Fehlerprotokoll des letzten Laufs
└── put_vocab_db_here/         # Hier die Kindle vocab.db ablegen
```

## ⚙️ Konfiguration

Bearbeite `kindle_to_anki/config.py` zum Anpassen:

```python
CONFIG = {
    # API & Pfade
    'GEMINI_API_KEY': 'dein-api-key',
    'VOCAB_DB_PATH': 'put_vocab_db_here/vocab.db',
    'TSV_OUTPUT_DIR': 'anki_cards/tsv_files',
    'APKG_OUTPUT_DIR': 'anki_cards/apkg_files',
    
    # Batch-Einstellungen (für aktuelle kostenlose API-Limits: 15 RPM, 1M TPM, 200 RPD)
    'BATCH_SIZE': 20,
    'DELAY_BETWEEN_BATCHES': 4.5,  # Sekunden
    
    # Ausgabe-Optionen
    'CREATE_EN_DE_CARDS': True,     # Englisch → Deutsch
    'CREATE_DE_EN_CARDS': True,     # Deutsch → Englisch
    'CREATE_DE_DE_CARDS': True,     # Deutsch → Deutsch
    'CREATE_APKG': True,            # APKG-Pakete automatisch erstellen
    
    # Debugging
    'VERBOSE': False,               # Detaillierte Fortschrittsanzeige
    'SAVE_RAW_RESPONSES': False,    # Gemini-Antworten speichern (Debug)
    'SAVE_RAW_INPUTS': False,       # Prompts speichern (Debug)
}
```

## 🎨 Kartendesign

### EN→DE Karten (Blaues Theme)
- **Vorderseite**: Englisches Wort + Kontext
- **Rückseite**: Deutsche Übersetzung + Definition + Notizen

### DE→EN Karten (Rotes Theme) - mit Cloze
- **Vorderseite**: Deutsche Übersetzung + Kontext (mit verstecktem Lückentext-Original-Wort)
- **Rückseite**: Englisches Wort + Definition + Notizen

### DE→DE Karten (Türkises Theme)
- **Vorderseite**: Deutsches Wort + Kontext
- **Rückseite**: Deutsche Definition + Notizen

**Alle Karten enthalten:**
- 📚 Quellbuch
- 📝 Kontextsatz (Wort hervorgehoben oder versteckt)
- 💡 Sprachliche Hinweise (Register, Phrasal Verbs, Idiome, etc.)
- 🌙 Night Mode Support
- 📱 Responsive Design

## 🔄 Workflow

```mermaid
graph LR
    A[Kindle vocab.db] --> B[spaCy Lemmatisierung]
    B --> C[Gemini API]
    C --> D[Minimales JSON]
    D --> E[Python Rekonstruktion]
    E --> F[TSV-Dateien]
    F --> G[genanki]
    G --> H[APKG-Pakete]
    H --> I[Anki Import]
```

**Token-Optimierung:**
- Gemini generiert nur: `EN_definition`, `DE_gloss`, `Notes`
- Python ergänzt: `Original_word`, `Lemma`, `Context_HTML`, `Book`
- **Einsparung**: ~59% weniger Output-Tokens

## 🌍 Unterstützte Sprachen

Der Converter unterstützt derzeit folgende Sprachen:

| Sprache | Code | spaCy-Modell | Status |
|---------|------|--------------|--------|
| 🇩🇪 Deutsch (German) | `de` | `de_core_news_sm` | ✅ Vollständig unterstützt |
| 🇬🇧 Englisch (English) | `en` | `en_core_web_sm` | ✅ Vollständig unterstützt |
| 🇪🇸 Spanisch (Español) | `es` | `es_core_news_sm` | ✅ Vollständig unterstützt |
| 🇫🇷 Französisch (Français) | `fr` | `fr_core_news_sm` | ✅ Vollständig unterstützt |
| 🇵🇱 Polnisch (Polski) | `pl` | `pl_core_news_sm` | ✅ Vollständig unterstützt |

**Konfiguriere dein Sprachpaar** in `kindle_to_anki/config.py`:
```python
CONFIG = {
    'SOURCE_LANGUAGE': 'de',  # Deine Muttersprache (Karten & Prompts)
    'TARGET_LANGUAGE': 'en',  # Sprache, die du lernst (Kindle-Buch)
    ...
}
```

> 💡 **Das Skript erkennt automatisch, welche spaCy-Modelle du brauchst!** Wenn du das Skript ausführst, sagt es dir genau, welche Modelle du installieren musst, falls sie fehlen.

**Fehlt deine Sprache?** [Erstelle ein Issue auf GitHub](https://github.com/MattisBeck/kindle-to-anki/issues) und bitte um Unterstützung für deine Sprache!

## 📊 Beispiel-Ausgabe

**Beispiel-Lauf (360 EN + 528 DE Wörter):**
```
✅ TSV erstellt: anki_en_de.tsv (360 Karten)
✅ TSV erstellt: anki_de_en.tsv (360 Karten)
✅ TSV erstellt: anki_de_de.tsv (528 Karten)

✅ APKG erstellt: anki_en_de.apkg (360 Karten)
✅ APKG erstellt: anki_de_en.apkg (360 Karten)
✅ APKG erstellt: anki_de_de.apkg (528 Karten)
```

## 🛠️ Fehlerbehebung

### spaCy-Modelle fehlen
Das Skript sagt dir, welche Modelle du brauchst. Führe einfach den vorgeschlagenen Befehl aus, zum Beispiel:
```bash
python -m spacy download de_core_news_sm
python -m spacy download en_core_web_sm
```

### Gemini API Quota überschritten
- Free-Tier: 15 RPM, 1.000.000 TPM, 200 RPD
- Anpassen: `BATCH_SIZE` (kleiner) und `DELAY_BETWEEN_BATCHES` (länger)

### APKG-Generierung fehlgeschlagen
```bash
pip install genanki
```

## 💡 Tipps

1. **Cache nutzen**: Bei weiteren Durchläufen werden nur neue Vokabeln übersetzt
2. **Batch-Größe anpassen**: Kleinere Batches = bessere Qualität, langsamere Verarbeitung
3. **VERBOSE aktivieren**: Setze `VERBOSE=True` für detaillierte Debug-Ausgabe
4. **TSV manuell bearbeiten**: Bearbeite TSV-Dateien in Excel oder Numbers vor der APKG-Erstellung, du kannst den Konverter separat ausführen:
   ```bash
   python tsv_to_apkg.py
   ```
5. **Buchtitel-Normalisierung**: Titel werden automatisch für Konsistenz normalisiert

## 🤝 Mitwirken

Beiträge sind willkommen! Bitte:
1. Forke das Repository
2. Erstelle einen Feature-Branch
3. Mache deine Änderungen
4. Reiche einen Pull Request ein

## 📝 Lizenz

MIT-Lizenz - Frei verwendbar für private und kommerzielle Zwecke.

## 🙏 Credits
- **Anki** - dank Anki, hatte ich nicht nur gute Noten, sondern ohne Anki, wäre dieses Projekt nie entstanden
- **GitHub Student Developer Pack** - Ohne das Developer pack, hätte ich keinen Zugriff auf GitHub Copilot und das Projekt wäre für mich nicht realisierbar gewesen.
- **Gemini 2.0 Flash** (Google) - KI-generierte Definitionen
- **spaCy** - Automatische Lemmatisierung
- **genanki** - APKG-Paket-Generierung
- **Ultimate Geography** - Design-Inspiration

---

Viel Erfolg beim Vokabellernen! 🎉