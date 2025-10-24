#!/usr/bin/env python3
"""
TSV to APKG Converter Wrapper
Simple entry point that delegates to the apkg_builder module
"""

from pathlib import Path
from kindle_to_anki.apkg_builder import convert_all_tsv_to_apkg


def main():
    """Main function for standalone execution"""
    print("=" * 70)
    print("TSV to APKG Converter")
    print("=" * 70)
    print()
    
    # Default paths
    tsv_dir = Path('anki_cards/tsv_files')
    apkg_dir = Path('anki_cards/apkg_files')
    
    print(f"📂 TSV-Verzeichnis: {tsv_dir}")
    print(f"📦 APKG-Verzeichnis: {apkg_dir}")
    print()
    
    # Convert all TSV files
    results = convert_all_tsv_to_apkg(tsv_dir, apkg_dir)
    
    # Summary
    print()
    print("=" * 70)
    print("Zusammenfassung:")
    successful = sum(1 for success in results.values() if success)
    print(f"  - Erfolgreich konvertiert: {successful}/{len(results)}")
    
    if successful > 0:
        print()
        print("🎉 APKG-Dateien können jetzt in Anki importiert werden!")
        print("   Die Karten enthalten die Ultimate UX V2 Templates mit:")
        print("   ✅ Progressive Disclosure")
        print("   ✅ Night Mode Support")
        print("   ✅ Farbcodierte Antworten (Blau/Rot/Türkis)")
        print("   ✅ Responsive Design für Mobile")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
