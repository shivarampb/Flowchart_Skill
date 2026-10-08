#!/usr/bin/env python3
"""Launch the ANSI/ISO 5807:1985 flowchart MCP server (stdio by default; --help for options).

Needs only Python >= 3.9; no packages to install.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iso5807_mcp.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
