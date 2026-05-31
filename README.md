# Project Zomboid-style C++ Engine Prototype

A tiny isometric world-rendering prototype built with C++20, GLFW, OpenGL, GLM, and Assimp.

## Current features

- GLFW window and real-time game loop.
- GLM isometric camera math with perspective projection.
- Blue sky clear color.
- Simple ground grid to make movement visible.
- Loads `media/models/Bob.fbx` through Assimp and draws it in the world.
- Camera follows the character model instead of panning independently.
- WASD moves the character like Project Zomboid: up/down/left/right on screen across diagonal world-tile directions.
- Loads `media/anim_x/bob/Bob_Idle.fbx` and `media/anim_x/bob/Bob_Walk.fbx`, switches between idle/walk by movement state, and applies skeletal CPU skinning to the body mesh.
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
    Bob.fbx
  anim_x/
    bob/
      Bob_Idle.fbx
      Bob_Walk.fbx
```

The engine loads all three FBX files at startup with Assimp, prints how many model meshes, bones, and animation channels were found, renders the body mesh, and picks `Bob_Idle` while standing or `Bob_Walk` while WASD movement is active.

Animation now uses a first-pass skeletal CPU skinning path: `Bob.fbx` provides the skeleton, inverse bind matrices, and vertex bone weights; `Bob_Idle.fbx` and `Bob_Walk.fbx` provide animation channels; the engine matches channels to bones by normalized Blender-style names such as `Armature.008` -> `Armature`, samples position/rotation/scale keys each frame, builds final bone matrices, and skins vertices before drawing them. This is intentionally simple and should later move to VBO/VAO rendering with GPU skinning.
