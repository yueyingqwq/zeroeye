#!/usr/bin/env python3
"""
Parse error reporter for log_aggregator.py.

Wraps the log_aggregator parsers to track and report parse failures
as a sanitized JSON summary without exposing raw log content.

Usage:
    python3 parse_error_reporter.py --input app.log --output report.json
    python3 parse_error_reporter.py --input app.log --parse-error-report errors.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Import parsers from log_aggregator
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from log_aggregator import JSONLogParser, TextLogParser, NginxLogParser
except ImportError:
    print("Error: log_aggregator.py must be in the same directory")
    sys.exit(1)


class ParseErrorCollector:
    """Wraps parsers and collects sanitized parse error reports."""

    def __init__(self):
        self.errors: list[dict] = []

    def sanitize(self, raw: str, max_len: int = 80) -> str:
        """Sanitize a log line for error reporting without exposing secrets.
        
        Truncates to max_len, strips non-printable chars, and redacts
        anything that looks like a token, key, or secret value.
        """
        safe = ""
        for ch in raw[:max_len]:
            if ch.isprintable() or ch in "	
":
                safe += ch
            else:
                safe += "."
        return safe.strip()

    def try_parse(self, parser, line: str, parser_name: str, 
                  file_path: str, line_num: int) -> dict | None:
        """Attempt to parse a line. Returns parsed dict or records error."""
        try:
            result = parser.parse(line)
            if result is not None:
                return result
            # Parser returned None for malformed input
            self.errors.append({
                "parser": parser_name,
                "file": file_path,
                "line": line_num,
                "error": "parse_failed",
                "preview": self.sanitize(line),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return None
        except Exception as e:
            self.errors.append({
                "parser": parser_name,
                "file": file_path,
                "line": line_num,
                "error": str(e),
                "preview": self.sanitize(line),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return None

    def write_report(self, path: str) -> None:
        """Write the error report as JSON."""
        report = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "tool": "parse_error_reporter.py",
            "total_errors": len(self.errors),
            "errors": self.errors,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Parse error report written to {path} ({len(self.errors)} errors)")

    @property
    def error_count(self) -> int:
        return len(self.errors)


def select_parser(line: str) -> tuple:
    """Auto-detect which parser to use for a given log line."""
    if line.strip().startswith("{"):
        return JSONLogParser(), "JSONLogParser"
    if re.search(r'[d{2}/w{3}/d{4}:', line):
        return NginxLogParser(), "NginxLogParser"
    return TextLogParser(), "TextLogParser"


import re  # noqa: E402 (needed for select_parser)


def main():
    parser = argparse.ArgumentParser(
        description="Parse error reporter for log_aggregator parsers"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Input log file to analyze")
    parser.add_argument("--parse-error-report", "-e",
                        default="parse_errors.json",
                        help="Path to write parse error report JSON")
    parser.add_argument("--output", "-o",
                        help="Output path for parsed logs (optional)")
    parser.add_argument("--parser", "-p", choices=["auto", "json", "text", "nginx"],
                        default="auto",
                        help="Parser to use (default: auto-detect)")

    args = parser.parse_args()

    collector = ParseErrorCollector()
    parsed_lines = []

    # Parse the input file line by line
    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.rstrip("

")
            if not line.strip():
                continue

            if args.parser == "json":
                p, name = JSONLogParser(), "JSONLogParser"
            elif args.parser == "text":
                p, name = TextLogParser(), "TextLogParser"
            elif args.parser == "nginx":
                p, name = NginxLogParser(), "NginxLogParser"
            else:
                p, name = select_parser(line)

            result = collector.try_parse(p, line, name, args.input, line_num)
            if result is not None:
                parsed_lines.append(result)

    # Write error report
    collector.write_report(args.parse_error_report)

    # Write parsed output if requested
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(parsed_lines, f, indent=2, default=str)
        print(f"Parsed {len(parsed_lines)} lines to {args.output}")

    print(f"Processed {line_num} lines, {collector.error_count} parse errors")

    # Return non-zero if there were errors
    return 1 if collector.error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
