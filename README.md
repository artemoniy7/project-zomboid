# Project Zomboid-style C++ Engine Prototype

A tiny isometric world-rendering prototype built with C++20, GLFW, OpenGL, GLM, and Assimp.

## Current features

- GLFW window and real-time game loop.
- GLM isometric camera math with orthographic projection, using Project Zomboid-style 60° FOV plus a 45° horizontal yaw and 30° downward pitch for 2:1 dimetric tile alignment.
- Blue sky clear color.
- Simple ground grid to make movement visible; its cell spacing is derived from the ground tile width so the visible world grid fits the tile art instead of oversized cells.
- Loads the Tiles1x texture pack and fills the ground tile layer with `blends_natural_01_TEST_22` beneath the rest of the scene.
- Loads `media/models/Bob.fbx` through Assimp and draws it in the world.
- Camera follows the character model instead of panning independently.
- WASD moves the character like Project Zomboid: up/down/left/right on screen across diagonal world-tile directions.
- Loads `media/anim_x/bob/Bob_Idle.fbx`, `media/animations/Bob_IdleToWalk.fbx`, `media/anim_x/bob/Bob_Walk.fbx`, and `media/animations/Bob_WalkToStop.fbx`, plays start/stop transition clips around walk, and applies skeletal CPU skinning to the body mesh.
- Applies `media/textures/Body MaleBody01.png` to the player model when the PNG and model UVs are available.
- Falls back to a basic colored cube when the model file is missing.

## Controls

| Input | Action |
| --- | --- |
| `W` / `S` | Move up / down on screen across diagonal tiles |
| `A` / `D` | Move left / right on screen across diagonal tiles |
| Mouse wheel | Zoom camera in / out |
| `Esc` | Close the window |

## Tuning movement and animation speed

Movement speed is controlled by `CharacterMoveSpeed` near the top of `main.cpp`. Looping animation playback speed is controlled separately by `CharacterAnimationPlaybackSpeed`, while one-shot start/stop clips use `CharacterTransitionAnimationPlaybackSpeed` so they can stay snappy without speeding up idle/walk loops. When movement keys are released, `CharacterStopCoastSpeedScale` controls the small decelerating forward coast during `Bob_WalkToStop`. Use values below `1.0F` to slow animation down or above `1.0F` to speed it up.

## Collision editor

A small Python/Tkinter utility is available for authoring per-tile collision metadata without hard-coding shapes in C++:

```bash
python3 tools/collision_editor.py media/texturepacks/Tiles1x
python3 tools/collision_editor.py media/texturepacks/Tiles1x/Tiles_Test.png
```

Use **Open folder** to load every atlas in a texture-pack directory, or **Open PNG atlas** to pick one `.png` file directly. The editor reads the matching atlas `.toml`, including multi-line `pos`/`size` arrays, cuts the atlas into individual tile sprites, automatically selects the first loaded tile, lets you switch with **Prev tile** / **Next tile**, and draws the selected sprite over a projected in-game-style cell guide. Draw rectangle or circle collision shapes over the tile, or add a full-tile collision. **Save collisions.toml** writes normalized collision data next to the tile metadata. The engine loads `collisions.toml` from the same texture-pack directory at startup and reports how many collision shapes were found; movement resolution can then consume those definitions when the collision world is wired in.

## Build

Install development packages for GLFW, GLM, OpenGL, and Assimp, then run:

```bash
cmake -S . -B build
cmake --build build
./build/pz_engine
```

If you want to compile the single source file directly with `g++` instead of CMake, use `pkg-config` to ask GLFW for the required compiler and linker flags. The `$()` part is important on Linux/macOS shells: it runs `pkg-config` first and substitutes its output into the `g++` command.

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine $(pkg-config --cflags --libs glfw3 assimp) -lGL -lz
./pz_engine
```

If your compiler complains about `--cflags` or `--libs`, those flags were passed to `g++` directly instead of being executed by `pkg-config`. Do not remove `$()` in Bash/Zsh. You can also run the two steps manually and paste the first command's output into the second command:

```bash
pkg-config --cflags --libs glfw3 assimp
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine <paste pkg-config output here> -lGL -lz
```

On Windows `cmd.exe` or PowerShell, `$(...)` does not work the same way as in Bash. Prefer the CMake build there, or use a MinGW/MSYS2 shell where `pkg-config` works. A typical MinGW manual link command looks like this, but library paths can differ on your machine:

```bash
g++ -std=c++20 -Wall -Wextra -Wpedantic main.cpp -o pz_engine.exe -lglfw3 -lassimp -lopengl32 -lgdi32 -lz
```

GLM is header-only, so it does not need an extra linker flag. The `-lz` flag is required by the PNG loader. If `pkg-config` cannot find `glfw3` or `assimp`, install the matching development package first or use the CMake build above.

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
  animations/
    Bob_IdleToWalk.fbx
    Bob_WalkToStop.fbx
  textures/
    Body MaleBody01.png
```

The engine loads all player FBX files at startup with Assimp, prints how many model meshes, bones, and animation channels were found, renders the body mesh, applies `Body MaleBody01.png` through the model UVs when present, and picks `Bob_Idle` while standing. When WASD movement starts it plays `Bob_IdleToWalk` once, then loops `Bob_Walk` while movement stays active. When movement stops it plays `Bob_WalkToStop` once, gently coasts forward in the last facing direction while that stop clip plays, then returns to `Bob_Idle`.

Animation now uses a first-pass skeletal CPU skinning path: `Bob.fbx` provides the skeleton, inverse bind matrices, and vertex bone weights; `Bob_Idle.fbx`, `Bob_IdleToWalk.fbx`, `Bob_Walk.fbx`, and `Bob_WalkToStop.fbx` provide animation channels; the engine matches channels to bones by normalized Blender-style names such as `Armature.008` -> `Armature` and namespace/action-style names such as `Armature|Bip01_Pelvis` -> `Bip01_Pelvis`, samples keys each frame, builds final bone matrices, and skins vertices before drawing them. Walk/stop locomotion clips are retargeted from their first frame while keeping the model bind-pose bone translations/scales, so exported FBX local translation keys (for example from `.011` Blender object copies) do not stretch the legs or push feet too far forward. `Bob_IdleToWalk` keeps its authored rotations instead of first-frame rotation retargeting, while still ignoring exported local translation/scale keys; this preserves the Blender start-step pose and avoids an exaggerated high leg lift. At startup it prints how many animation channels match model bones, which helps diagnose exported clips like `Bob_Walk.fbx`. This is intentionally simple and should later move to VBO/VAO rendering with GPU skinning.
