#!/usr/bin/env python
"""
Cross-platform (Windows-friendly) launcher for llama-cpp-python

Installation prerequisites (PowerShell):
    python -m pip install --upgrade llama-cpp-python psutil

Usage examples:
    python "install llama.py"                                         # uses defaults
    python "install llama.py" --model ./language_models/gemma.gguf    # explicit model
    python "install llama.py" --threads 6 --ctx 8192                  # tune threads/ctx
    LLAMA_NUM_THREADS=8 python "install llama.py"                     # env-var override
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import contextlib
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Optional, do-not-crash imports
try:
    import psutil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psutil = None  # type: ignore

from llama_cpp import Llama


# --------------------------------------------------------------------------- #
# Helper utilities
def human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    for u in units:
        if num < 1024:
            return f"{num:.1f}{u}"
        num /= 1024
    return f"{num:.1f}EB"


def logical_cores() -> int:
    """Return logical core count; always ≥ 1."""
    return max(1, os.cpu_count() or 1)


def default_threads() -> int:
    """Half the logical cores, minimum 1."""
    return max(1, logical_cores() // 2)


@contextlib.contextmanager
def suppress_stderr():
    """Temporarily suppress stderr output."""
    with open(os.devnull, "w") as devnull:
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stderr = old_stderr


# --------------------------------------------------------------------------- #
# Streaming output helper
class TokenStreamer:
    """
    Collects tokens from llama_cpp stream=True and prints them immediately.
    Tracks token count and timing for performance stats.
    """

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self.tokens_generated = 0
        self.text_parts: list[str] = []

    def __call__(self, chunk: dict) -> None:  # noqa: D401
        token = chunk["choices"][0]["delta"].get("content", "")
        if token:
            self.text_parts.append(token)
            print(token, end="", flush=True)
            self.tokens_generated += 1

    def done(self) -> None:
        print()  # final newline
        elapsed = time.perf_counter() - self._start
        if elapsed:
            print(f"\nAverage speed: {self.tokens_generated/elapsed:.2f} tok/s")


# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Portable llama-cpp-python chat demo with streaming output."
    )
    parser.add_argument(
        "--model",
        "--model-path",
        dest="model_path",
        type=Path,
        default=Path("language_models/gemma-3n-E2B-it-Q8_0.gguf"),
        help="Path to .gguf model file (default: %(default)s)",
    )
    parser.add_argument(
        "--threads",
        "-t",
        type=int,
        default=int(os.getenv("LLAMA_NUM_THREADS", default_threads())),
        help="Number of CPU threads (default: half logical cores)",
    )
    parser.add_argument(
        "--ctx",
        type=int,
        default=32768,
        help="Context window size (default: %(default)s)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default=(
            "Write me a story where Minecraft Herobrine fights Dr. Eggman. "
            "You must decide a victor."
        ),
        help="Prompt to send to the model.",
    )
    parser.add_argument(
        "--max-tokens",
        "-m",
        type=int,
        default=30000,
        help="Maximum tokens to generate (default: %(default)s)",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
def main() -> None:  # noqa: D401
    args = parse_args()

    model_path: Path = args.model_path.expanduser().resolve()
    if not model_path.is_file():
        print(f"[ERROR] Model file not found: {model_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Model      : {model_path}")
    print(f"Threads    : {args.threads} / {logical_cores()} logical cores")
    print(f"Context    : {args.ctx}")
    print(f"Prompt     : {args.prompt[:60]}{'...' if len(args.prompt) > 60 else ''}")
    print("Loading model... (this may take a minute)")

    # Memory snapshot before loading
    rss_before: Optional[int] = None
    if psutil:
        rss_before = psutil.Process(os.getpid()).memory_info().rss

    t_load_start = time.perf_counter()
    
    # Suppress Metal kernel messages during model loading
    with suppress_stderr():
        llm = Llama(
            model_path=str(model_path),
            chat_format="gemma",
            n_threads=args.threads,
            n_ctx=args.ctx,
            verbose=False,
        )
    
    print(f"Model loaded in {time.perf_counter() - t_load_start:.1f}s")
    print("Generating response...\n")

    # ----------------------------------- #
    # Streaming generation
    streamer = TokenStreamer()
    stream = llm.create_chat_completion(
        messages=[{"role": "user", "content": args.prompt}],
        max_tokens=args.max_tokens,
        temperature=1.0,
        top_p=0.95,
        top_k=64,
        stream=True,
    )

    for chunk in stream:
        streamer(chunk)

    streamer.done()
    # ----------------------------------- #

    # Final statistics
    rss_after: Optional[int] = None
    if psutil:
        rss_after = psutil.Process(os.getpid()).memory_info().rss

    if rss_before is not None and rss_after is not None:
        print("======== Memory Usage ========")
        print(f"RSS before : {human_bytes(rss_before)}")
        print(f"RSS after  : {human_bytes(rss_after)}")
        print(f"Δ RSS      : {human_bytes(rss_after - rss_before)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")