Perfecte! Anem a implementar l'Opció 1 pas a pas.
📋 PAS 1: Crear l'script Python
Crea un nou fitxer al teu repositori anomenat generate_index.py:
python#!/usr/bin/env python3
"""
Script per generar un índex de tots els partits
Executa automàticament amb GitHub Actions
"""
import json
import os
from pathlib import Path
from datetime import datetime

def generate_matches_index():
    # Buscar tots els fitxers de partits (cnt_stats_*.json)
    match_files = sorted([
        f.name for f in Path('.').glob('cnt_stats_*.json')
    ], reverse=True)  # Més recents primer
    
    # Crear l'índex
    index = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_matches": len(match_files),
        "files": match_files
    }
    
    # Guardar l'índex
    with open('matches_index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Índex generat: {len(match_files)} partits")
    for f in match_files:
        print(f"   - {f}")
    
    return len(match_files)

if __name__ == "__main__":
    count = generate_matches_index()
    print(f"\n✅ matches_index.json creat amb {count} partits")