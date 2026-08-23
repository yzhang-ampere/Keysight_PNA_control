"""Backward-compatible launcher for the reorganized PNA applications."""

import sys


if __name__ == "__main__":
    if "--gui" in sys.argv:
        sys.argv.remove("--gui")
        from pna_gui import main
    else:
        from pna_script import main
    main()
