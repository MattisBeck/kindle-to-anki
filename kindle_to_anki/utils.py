"""
Utility functions for logging, progress tracking, and error handling
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from .helpers import build_field_key


def log_error(message: str, error_file: str = 'anki_cards/errors.log', verbose: bool = False):
    """
    Log error message to file
    
    Args:
        message: Error message to log
        error_file: Path to error log file
        verbose: Print to console
    """
    try:
        # Create directory if needed
        error_path = Path(error_file)
        error_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        
        # Append to file
        with open(error_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        if verbose:
            print(f"  ❌ {message}")
    
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Failed to log error: {e}")


def save_progress(data: Dict, progress_file: str, verbose: bool = False):
    """
    Save progress to JSON file
    
    Args:
        data: Progress data dictionary
        progress_file: Path to progress JSON file
        verbose: Enable verbose output
    """
    try:
        # Create directory if needed
        progress_path = Path(progress_file)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp
        data['last_updated'] = datetime.now().isoformat()
        
        # Save with pretty formatting
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        if verbose:
            print(f"  💾 Progress saved: {progress_file}")
    
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Failed to save progress: {e}")


def load_progress(progress_file: str, verbose: bool = False) -> Optional[Dict]:
    """
    Load progress from JSON file
    
    Args:
        progress_file: Path to progress JSON file
        verbose: Enable verbose output
        
    Returns:
        Progress dictionary or None if not found
    """
    if not Path(progress_file).exists():
        return None
    
    try:
        with open(progress_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if verbose:
            last_updated = data.get('last_updated', 'unknown')
            print(f"  📂 Progress loaded (last updated: {last_updated})")
        
        return data
    
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Failed to load progress: {e}")
        return None


def format_time(seconds: float) -> str:
    """
    Format seconds to human-readable time
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string (e.g., "2m 30s" or "45s")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours}h {remaining_minutes}m"


def print_stats(deck_counts: Dict[str, int], cache_stats: Dict,
               processing_time: float = 0, verbose: bool = True):
    """
    Print processing statistics
    
    Args:
        en_cards: List of English cards
        de_cards: List of German cards
        cache_stats: Cache statistics dictionary
        processing_time: Total processing time in seconds
        verbose: Enable verbose output
    """
    if not verbose:
        return
    
    print("\n" + "="*60)
    print("📊 PROCESSING STATISTICS")
    print("="*60)
    
    # Card counts
    print("\n📚 Cards Created:")
    total_cards = 0
    for label, count in deck_counts.items():
        print(f"  • {label}: {count} cards")
        total_cards += count
    print(f"  • TOTAL:           {total_cards} cards")
    
    # Cache stats
    print(f"\n💾 Cache Statistics:")
    print(f"  • Total cached:    {cache_stats.get('total', 0)} words")
    for lang, count in cache_stats.items():
        if lang == 'total':
            continue
        print(f"  • {lang.upper()}:        {count} words")
    
    # Performance
    if processing_time > 0:
        print(f"\n⏱️  Performance:")
        print(f"  • Total time:      {format_time(processing_time)}")
        
        if total_cards > 0:
            avg_time = processing_time / total_cards
            print(f"  • Avg per card:    {avg_time:.2f}s")
    
    print("\n" + "="*60)


def count_api_calls(cards: List[Dict], cache: Dict, language: str) -> int:
    """
    Count how many API calls will be needed for a batch
    
    Args:
        cards: List of card dictionaries
        cache: Cache dictionary
        language: 'en' or 'de'
        
    Returns:
        Number of API calls needed
    """
    language = language.lower()
    bucket = cache.get('languages', {}).get(language, {})
    lemma_key = build_field_key(language, 'lemma')
    cached_lemmas = {
        card.get(lemma_key, '').lower()
        for card in bucket.values()
        if card.get(lemma_key)
    }

    new_cards = 0
    for card in cards:
        lemma = card.get(lemma_key, '').lower()
        if lemma and lemma not in cached_lemmas:
            new_cards += 1

    return new_cards


def create_backup(source_file: str, backup_dir: str = 'backups', verbose: bool = False) -> Optional[str]:
    """
    Create timestamped backup of a file
    
    Args:
        source_file: File to backup
        backup_dir: Backup directory
        verbose: Enable verbose output
        
    Returns:
        Path to backup file or None if failed
    """
    try:
        source_path = Path(source_file)
        
        if not source_path.exists():
            return None
        
        # Create backup directory
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_path / f"{source_path.stem}_{timestamp}{source_path.suffix}"
        
        # Copy file
        import shutil
        shutil.copy2(source_file, backup_file)
        
        if verbose:
            print(f"  💾 Backup created: {backup_file}")
        
        return str(backup_file)
    
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Backup failed: {e}")
        return None


def clean_old_backups(backup_dir: str = 'backups', keep_last: int = 5, verbose: bool = False):
    """
    Remove old backup files, keeping only the most recent ones
    
    Args:
        backup_dir: Backup directory
        keep_last: Number of recent backups to keep
        verbose: Enable verbose output
    """
    try:
        backup_path = Path(backup_dir)
        
        if not backup_path.exists():
            return
        
        # Get all backup files
        backup_files = sorted(backup_path.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Remove old backups
        for old_file in backup_files[keep_last:]:
            old_file.unlink()
            if verbose:
                print(f"  🗑️  Removed old backup: {old_file.name}")
    
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Backup cleanup failed: {e}")
