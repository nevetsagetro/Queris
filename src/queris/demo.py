"""Launch the local Streamlit demo."""

import sys
from pathlib import Path


def main() -> None:
    """Run the packaged Streamlit application."""
    from streamlit.web import cli

    app_path = Path(__file__).with_name("streamlit_app.py")
    sys.argv = ["streamlit", "run", str(app_path), *sys.argv[1:]]
    raise SystemExit(cli.main())
