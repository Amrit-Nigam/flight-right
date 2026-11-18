"""Refresh the consolidated latest evaluation, or manage model ledgers via --help.

The former publisher recreated duplicate metrics/history files and omitted speech.
All model evaluation evidence now lives in docs/evaluations/<model>.md.
"""
import sys

from consolidate_evaluations import main, refresh, verify


if __name__ == "__main__":
    if len(sys.argv) == 1:
        refresh()
        verify()
    else:
        main()
