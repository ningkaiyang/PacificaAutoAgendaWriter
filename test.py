import sys, importlib.metadata, llama_cpp
from pathlib import Path

print("python      :", sys.executable)
print("llama-cpp-py:", importlib.metadata.version("llama_cpp_python"))
print("module file :", Path(llama_cpp.__file__).resolve())
print("'print_timings' in dir(Llama):", "print_timings" in dir(llama_cpp.Llama))