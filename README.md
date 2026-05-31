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

On Ubuntu-like systems the package names are typically similar to:

```bash
sudo apt install cmake g++ libglfw3-dev libglm-dev libgl1-mesa-dev libglx-dev
```
