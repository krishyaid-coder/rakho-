from __future__ import annotations

import os
import sys

SAFFRON = "\033[38;2;224;134;60m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Big wordmark. The two dots are the bindu — same mark as the logo.
_MARK = r"""
                         {s}●{r}
  {b}██████╗  █████╗ ██╗  ██╗██╗  ██╗ ██████╗{r}
  {b}██╔══██╗██╔══██╗██║ ██╔╝██║  ██║██╔═══██╗{r}
  {b}██████╔╝███████║█████╔╝ ███████║██║   ██║{r}
  {b}██╔══██╗██╔══██║██╔═██╗ ██╔══██║██║   ██║{r}
  {b}██║  ██║██║  ██║██║  ██╗██║  ██║╚██████╔╝{r}
  {b}╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝{r}
                         {s}●{r}
"""

_PLAIN = r"""
                         ●
  ██████╗  █████╗ ██╗  ██╗██╗  ██╗ ██████╗
  ██╔══██╗██╔══██╗██║ ██╔╝██║  ██║██╔═══██╗
  ██████╔╝███████║█████╔╝ ███████║██║   ██║
  ██╔══██╗██╔══██║██╔═██╗ ██╔══██║██║   ██║
  ██║  ██║██║  ██║██║  ██╗██║  ██║╚██████╔╝
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝
                         ●
"""


def _color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("RAKHO_NO_BANNER"):
        return False
    stream = sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def render_banner() -> str:
    if _color():
        art = _MARK.format(s=SAFFRON, b=BOLD, r=RESET)
    else:
        art = _PLAIN
    tag = "  र   keep it.   forget for real."
    if _color():
        tag = f"  {SAFFRON}र{RESET}   {DIM}keep it.   forget for real.{RESET}"
    return art.rstrip() + "\n\n" + tag + "\n"


def render_hints() -> str:
    lines = [
        "  rakho keep  --actor krishy \"order is late\"",
        "  rakho nikaalo --actor krishy \"order\"",
        "  rakho bhoolo --actor krishy",
        "  rakho dekho --actor krishy",
        "  rakho --gate sluice keep --actor krishy \"order is late\"",
    ]
    body = "\n".join(lines)
    if _color():
        return f"\n{DIM}  try{RESET}\n{body}\n"
    return f"\n  try\n{body}\n"


def print_banner(*, hints: bool = True) -> None:
    if os.environ.get("RAKHO_NO_BANNER"):
        return
    sys.stdout.write(render_banner())
    if hints:
        sys.stdout.write(render_hints())
    sys.stdout.flush()
