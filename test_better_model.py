#!/usr/bin/env python
"""
Cross-platform (Windows-friendly) launcher for llama-cpp-python

Installation prerequisites (PowerShell):
    python -m pip install --upgrade llama-cpp-python psutil

Usage examples:
    python "install llama.py"                                         # uses defaults
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
    # return logical core count always at least 1
    return max(1, os.cpu_count() or 1)

def default_threads() -> int:
    # half the logical cores minimum 1
    return max(1, logical_cores() // 2)

@contextlib.contextmanager
def suppress_stderr():
    # temporarily suppress stderr output
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
        self.text_buffer = ""  # we'll buffer text here until we pass the thinking block
        self.think_block_passed = False  # a flag to see if we are past the <think> block

    def __call__(self, chunk: dict) -> None:  # noqa: D401
        token = chunk["choices"][0]["delta"].get("content", "")
        if not token:
            return  # do nothing if there's no token

        self.tokens_generated += 1

        if not self.think_block_passed:
            # if we haven't passed the think block, add the token to our buffer
            self.text_buffer += token
            think_end_tag = "</think>"
            # check if the end tag is now in our buffer
            if think_end_tag in self.text_buffer:
                self.think_block_passed = True
                # find the content that comes after the tag
                content_to_print = self.text_buffer.split(think_end_tag, 1)[1]
                # print it, stripping any leading whitespace, and flush it to the console
                print(content_to_print.lstrip(), end="", flush=True)
        else:
            # if we are past the think block, just print tokens as they come
            print(token, end="", flush=True)

    def done(self) -> None:
        # if the model finished generating before ever passing a think block, print the whole buffer
        if not self.think_block_passed and self.text_buffer:
            print(self.text_buffer)
            
        elapsed = time.perf_counter() - self._start
        if elapsed:
            # print a newline to separate from the next potential output
            print(f"\nAverage speed: {self.tokens_generated/elapsed:.2f} tok/s")
            print(f"Tokens: {self.tokens_generated}")
            print(f"Elapsed Time: {elapsed:.2f}")

# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Portable llama-cpp-python chat demo with streaming output."
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
        default=20000,
        help="Context window size (default: %(default)s)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default=(
            "Hi! Who are you? How many letters are there in Strawbery? And how many Rs are there? And yes, I do mean to include the typo."
        ),
        help="Prompt to send to the model.",
    )
    parser.add_argument(
        "--max-tokens",
        "-m",
        type=int,
        default=20000,
        help="Maximum tokens to generate (default: %(default)s)",
    )
    return parser.parse_args()

# --------------------------------------------------------------------------- #
def main() -> None:  # noqa: D401
    args = parse_args()

    print(f"Threads    : {args.threads} / {logical_cores()} logical cores")
    print(f"Context    : {args.ctx}")
    print(f"Prompt     : {args.prompt[:60]}{'...' if len(args.prompt) > 60 else ''}")
    print("Loading model... (this may take a minute)")

    # memory snapshot before loading
    rss_before: Optional[int] = None
    if psutil:
        rss_before = psutil.Process(os.getpid()).memory_info().rss

    t_load_start = time.perf_counter()

    # suppress Metal kernel messages during model loading
    with suppress_stderr():
        llm = Llama(
            model_path="language_models/Qwen3-4B-Q6_K.gguf",  # using the local model path now
            chat_format="chatml",
            n_threads=args.threads,
            n_ctx=args.ctx,
            verbose=False,
        )
    print()  # make sure we end the progress line

    print(f"Model loaded in {time.perf_counter() - t_load_start:.1f}s")
    print("Generating response...\n")

    # ----------------------------------- #
    # Streaming generation
    streamer = TokenStreamer()
    stream = llm.create_chat_completion(
        messages=[{"role": "user", "content": args.prompt}],
        max_tokens=args.max_tokens,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
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
        print("\nInterrupted")