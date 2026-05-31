# Project Zomboid-style C++ Engine Prototype

A tiny first-person world-rendering prototype built with C++20, GLFW, OpenGL, and GLM.

## Current features

- GLFW window and real-time game loop.
- GLM camera math with perspective projection.
- Blue sky clear color.
- Simple ground grid to make movement visible.
- A basic colored cube in the world.
- WASD movement and mouse look.

## Controls

| Input | Action |
| --- | --- |
| `W` / `S` | Move forward / backward |
| `A` / `D` | Strafe left / right |
| Mouse | Rotate camera |
| `Space` | Move up |
| `Left Shift` | Move down |
| `Esc` | Close the window |

## Build

Install development packages for GLFW, GLM, and OpenGL, then run:

```bash
cmake -S . -B build
cmake --build build
./build/pz_engine
```

If you want to compile the single source file directly with `g++` instead of CMake, use `pkg-config` to ask GLFW for the required compiler and linker flags. The `$()` part is important on Linux/macOS shells: it runs `pkg-config` first and substitutes its output into the `g++` command.

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine $(pkg-config --cflags --libs glfw3) -lGL
./pz_engine
```

If your compiler complains about `--cflags` or `--libs`, those flags were passed to `g++` directly instead of being executed by `pkg-config`. Do not remove `$()` in Bash/Zsh. You can also run the two steps manually and paste the first command's output into the second command:

```bash
pkg-config --cflags --libs glfw3
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine <paste pkg-config output here> -lGL
```

On Windows `cmd.exe` or PowerShell, `$(...)` does not work the same way as in Bash. Prefer the CMake build there, or use a MinGW/MSYS2 shell where `pkg-config` works. A typical MinGW manual link command looks like this, but library paths can differ on your machine:

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine.exe -lglfw3 -lopengl32 -lgdi32
```

GLM is header-only, so it does not need an extra linker flag. If `pkg-config` cannot find `glfw3`, install the GLFW development package first or use the CMake build above.

On Ubuntu-like systems the package names are typically similar to:

```bash
sudo apt install cmake g++ libglfw3-dev libglm-dev libgl1-mesa-dev libglx-dev
```
