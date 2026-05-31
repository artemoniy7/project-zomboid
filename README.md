# Project Zomboid-style C++ Engine Prototype

A tiny isometric world-rendering prototype built with C++20, GLFW, OpenGL, GLM, and Assimp.

## Current features

- GLFW window and real-time game loop.
- GLM isometric camera math with perspective projection.
- Blue sky clear color.
- Simple ground grid to make movement visible.
- Loads `media/models/Bod.fbx` through Assimp and draws it in the world.
- Camera follows the character model instead of panning independently.
- WASD moves the character like Project Zomboid: up/down/left/right on screen across diagonal world-tile directions.
- Loads `media/anim_x/bob/Bob_Idle.fbx` and `media/anim_x/bob/Bob_Walk.fbx`, switches between idle/walk by movement state, and applies a small walk bob while moving when the walk clip is present.
- Falls back to a basic colored cube when the model file is missing.

## Controls

| Input | Action |
| --- | --- |
| `W` / `S` | Move up / down on screen across diagonal tiles |
| `A` / `D` | Move left / right on screen across diagonal tiles |
| Mouse wheel | Zoom camera in / out |
| `Esc` | Close the window |

## Build

Install development packages for GLFW, GLM, OpenGL, and Assimp, then run:

```bash
cmake -S . -B build
cmake --build build
./build/pz_engine
```

If you want to compile the single source file directly with `g++` instead of CMake, use `pkg-config` to ask GLFW for the required compiler and linker flags. The `$()` part is important on Linux/macOS shells: it runs `pkg-config` first and substitutes its output into the `g++` command.

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine $(pkg-config --cflags --libs glfw3 assimp) -lGL
./pz_engine
```

If your compiler complains about `--cflags` or `--libs`, those flags were passed to `g++` directly instead of being executed by `pkg-config`. Do not remove `$()` in Bash/Zsh. You can also run the two steps manually and paste the first command's output into the second command:

```bash
pkg-config --cflags --libs glfw3 assimp
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine <paste pkg-config output here> -lGL
```

On Windows `cmd.exe` or PowerShell, `$(...)` does not work the same way as in Bash. Prefer the CMake build there, or use a MinGW/MSYS2 shell where `pkg-config` works. A typical MinGW manual link command looks like this, but library paths can differ on your machine:

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine.exe -lglfw3 -lassimp -lopengl32 -lgdi32
```

GLM is header-only, so it does not need an extra linker flag. If `pkg-config` cannot find `glfw3` or `assimp`, install the matching development package first or use the CMake build above.

On Ubuntu-like systems the package names are typically similar to:

```bash
sudo apt install cmake g++ libglfw3-dev libglm-dev libassimp-dev libgl1-mesa-dev libglx-dev
```

## Assets

Use this asset layout:

```text
media/
  models/
    Bod.fbx
  anim_x/
    bob/
      Bob_Idle.fbx
      Bob_Walk.fbx
```

The engine loads all three FBX files at startup with Assimp, prints how many model meshes and animation channels were found, renders the body mesh, and picks `Bob_Idle` while standing or `Bob_Walk` while WASD movement is active.

The animation clips are currently loaded as metadata and used to drive the prototype animation state plus visible walk bob. To make the real skeletal FBX clips deform the model, the next engine step is to import a skeleton from `Bod.fbx`, import bone IDs/weights per vertex, match animation channels from `Bob_Idle.fbx` and `Bob_Walk.fbx` to bones by name, sample position/rotation/scale keys each frame, build final bone matrices, and skin vertices on the CPU or GPU.
