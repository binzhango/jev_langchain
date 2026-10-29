"""The full paired runner; all normal compare flags remain available."""
import sys
from jev_harness.cli import main

sys.argv.insert(1, "compare")
main()
