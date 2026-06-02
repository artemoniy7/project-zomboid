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
- Loads `media/anim_x/bob/Bob_Idle.fbx`, `media/anim_x/bob/Bob_IdleToWalk.fbx`, `media/anim_x/bob/Bob_Walk.fbx`, `media/anim_x/bob/Bob_WalkToStop.fbx`, `media/anim_x/bob/Bob_FallIdle.fbx`, and turn clips, plays movement/fall states, and applies skeletal CPU skinning to the body mesh.
- Applies `media/textures/Body MaleBody01.png` to the player model when the PNG and model UVs are available.
- Falls back to a basic colored cube when the model file is missing.

## Controls

| Input | Action |
| --- | --- |
| `W` / `S` | Move up / down on screen across diagonal tiles |
| `A` / `D` | Move left / right on screen across diagonal tiles |
| Mouse wheel | Zoom camera in / out |
| `Page Up` / `Page Down` | Move the character between walkable building levels |
| `Esc` | Close the window |


## Walkable levels and wall height

The engine now treats a **level** as one full wall-storey above the previous floor. In this prototype the wall-storey height is fixed by the tile-art scale: `TileSpriteWorldScale` converts pixels to world units (`1 / 64`), and `WorldLevelHeight` uses a 128-pixel wall frame, so each floor is `2.0` world units above the previous one. That makes level `0` ground, level `1` `2.0` units high, level `2` `4.0` units high, and so on.

This is intentionally derived from sprite dimensions instead of a guessed real-world meter value. If the wall art later uses a different storey frame height, change `LevelHeightInSpritePixels` near the tile constants in `main.cpp`; all walkable levels and the camera follow target will keep using the same formula.

When the character is on a level/tile position that has no walkable tile under it, the engine switches to `Bob_FallIdle.002`, locks movement and turning input, keeps the character facing the direction they were moving, and applies downward fall velocity until a lower supported tile is reached.

## Tuning movement and animation speed

Movement speed is controlled by `CharacterMoveSpeed` near the top of `main.cpp`. Looping animation playback speed is controlled separately by `CharacterAnimationPlaybackSpeed`, while one-shot start/stop clips use `CharacterTransitionAnimationPlaybackSpeed` so they can stay snappy without speeding up idle/walk loops. When movement keys are released, `CharacterStopCoastSpeedScale` controls the small decelerating forward coast during `Bob_WalkToStop`. Use values below `1.0F` to slow animation down or above `1.0F` to speed it up.

## Map editor

A Python/Tkinter map editor is available for painting tile maps and saving them under `saves/`:

```bash
python3 tools/map_editor.py
python3 tools/map_editor.py media/texturepacks/Tiles1x
python3 tools/map_editor.py media/texturepacks/Tiles1x/Tiles_Test.png --map saves/map_01.toml
```

The editor uses the same tile browser pattern as the collision editor: open a texture-pack folder or one PNG atlas from `media/texturepacks`, filter/select tiles from the atlas list, then left-click cells to place tiles and right-click to erase them. Use the **Level** control to edit world levels from `-10` to `10` and the **Layer** control to stack multiple tiles on the same cell. Tile sprites are cached after first use so repeated painting does not constantly crop atlas images. **Save map** / **Save map as** writes TOML maps into the `saves/` folder; the engine loads `saves/map_01.toml` at startup when it exists.

## Collision editor

A small Python/Tkinter utility is available for authoring per-tile collision metadata without hard-coding shapes in C++:

```bash
python3 tools/collision_editor.py media/texturepacks/Tiles1x
python3 tools/collision_editor.py media/texturepacks/Tiles1x/Tiles_Test.png
```

Use **Open folder** to load every atlas in a texture-pack directory, or **Open PNG atlas** to pick one `.png` file directly. The editor reads the matching atlas `.toml`, including multi-line `pos`/`size` arrays, cuts the atlas into individual tile sprites, automatically selects the first loaded tile, lets you switch with **Prev tile** / **Next tile**, and draws the selected sprite over a projected in-game-style cell guide anchored to the bottom of the sprite so tall/multi-story tiles get their floor collision at ground level. Draw rectangle, circle, or side/wall line collision shapes over the tile, add a full-tile collision, or add **Floor / walkable** collision to mark tiles that should support characters as floors instead of blocking objects. Full-tile and floor collision default to that bottom floor cell instead of the whole tall sprite. **Save collisions.toml** writes normalized collision data next to the tile metadata. The engine loads `collisions.toml` from the same texture-pack directory at startup and uses `floor` shapes from saved map tiles as walkable support for multi-level movement/falling.

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
