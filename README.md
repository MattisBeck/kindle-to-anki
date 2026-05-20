# Kindle to Anki

Create Anki decks from a Kindle `vocab.db` vocabulary database.

The tool reads the saved Kindle vocabulary, asks Gemini to translate and explain the words, and writes Anki `.apkg` deck files.

If this project helps you, please give it a star on GitHub.

[![GitHub Stars](https://img.shields.io/github/stars/MattisBeck/kindle-to-anki?style=social)](https://github.com/MattisBeck/kindle-to-anki/stargazers)

## Screenshots

<div align="center">

**EN->DE Cards (iOS)**  
<img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/iOS_en_de_light.gif" alt="EN->DE Light" width="180"/> <img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/iOS_en_de_dark.gif" alt="EN->DE Dark" width="180"/>

**DE->EN Cards (macOS)**  
<img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/macos_de_en_light.gif" alt="DE->EN Light" width="380"/> <img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/macos_de_en_dark.gif" alt="DE->EN Dark" width="380"/>

**DE->DE Cards (macOS)**  
<img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/macos_de_de_light.gif" alt="DE->DE Light" width="380"/> <img src="https://raw.githubusercontent.com/MattisBeck/github-assets/master/kindle-to-anki/macos_de_de_dark.gif" alt="DE->DE Dark" width="380"/>

</div>

## Requirements

- Python 3.14 or newer
- `uv`
- A Gemini API key
- A Kindle `vocab.db` file
- Anki, to import the generated `.apkg` files

## Get Started

1. Clone the repository.

   ```bash
   git clone https://github.com/MattisBeck/kindle-to-anki.git
   cd kindle-to-anki
   ```

2. Put your Kindle vocabulary database here:

   ```text
   put_vocab_db_here/vocab.db
   ```

3. Run the converter.

   ```bash
   uv run kindle-to-anki
   ```

   On the first run, the tool starts the setup if required. It asks for your native language code, batch size, Gemini API key, and Gemini model.

4. Import the generated `.apkg` files from `data/apkg/` into Anki.

`uv run` prepares the project environment automatically for normal use, so a separate `uv sync` step is not required.

## Useful Commands

Show all CLI options:

```bash
uv run kindle-to-anki --help
```

Show the current configuration and Gemini API status:

```bash
uv run kindle-to-anki --status
```

Run the setup again:

```bash
uv run kindle-to-anki --config
```

Use a custom Kindle database path:

```bash
uv run kindle-to-anki --db-path /path/to/vocab.db
```

Show progress while running:

```bash
uv run kindle-to-anki --verbose
```

## Output

Generated files are written under `data/`.

- `data/apkg/<LANGUAGE_PAIR>.apkg`: Anki decks to import, for example `DE->DE.apkg`
- `data/json/anki_cards.json`: generated card data
- `data/json/raw_response.json`: stored Gemini responses
- `data/json/cache.json`: words that were already processed

The `data/` directory and the local Kindle database are ignored by git.

## Development

Run the test suite:

```bash
uv run pytest
```
