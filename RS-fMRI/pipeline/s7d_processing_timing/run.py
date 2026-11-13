#!/usr/bin/env python3
"""Export per-stage and overall processing times without changing a calculation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '04_workflow'))
from processing_time import main

if __name__ == '__main__':
    main()
