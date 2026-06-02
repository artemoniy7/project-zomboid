#!/usr/bin/env python3
"""Map editor for the C++ Project Zomboid-style prototype.

The editor reuses the Tiles1x-style atlas metadata format used by the collision
editor, lets the user pick tiles from ``media/texturepacks`` folders, paints
those tiles on discrete world levels, and saves map files into ``saves/``.
"""

from __future__ import annotations

import argparse
import re
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_TITLE = "Project Zomboid Map Editor"
DEFAULT_TEXTUREPACKS_DIR = Path("media/texturepacks")
DEFAULT_SAVES_DIR = Path("saves")
MIN_LEVEL = -10
MAX_LEVEL = 10
MAP_HALF_SIZE = 20
TILE_SCREEN_WIDTH = 64
TILE_SCREEN_HEIGHT = 32
CANVAS_PADDING = 160
PNG_FILETYPES = (("PNG atlas", ("*.png", "*.PNG")), ("All files", "*.*"))
MAP_FILETYPES = (("Map TOML", ("*.toml", "*.TOML")), ("All files", "*.*"))


@dataclass(frozen=True)
class TileDef:
    name: str
    atlas_path: Path
    pos: tuple[int, int]
    size: tuple[int, int]
    frame_offset: tuple[int, int] = (0, 0)
    frame_size: tuple[int, int] = (64, 128)


@dataclass(frozen=True)
class MapTile:
    tile_name: str
    atlas_name: str


@dataclass
class EditorState:
    texturepack_folder: Path | None = None
    atlas_filter: Path | None = None
    tiles: list[TileDef] = field(default_factory=list)
    placements: dict[tuple[int, int, int, int], MapTile] = field(default_factory=dict)
    map_path: Path | None = None


def _strip_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:index]
    return line


def _parse_int_array(value: str) -> tuple[int, int] | None:
    numbers = [int(match) for match in re.findall(r"-?\d+", value)]
    if len(numbers) < 2:
        return None
    return numbers[0], numbers[1]


def _collect_toml_array_value(
    lines: list[str], line_index: int, value: str
) -> tuple[str, int]:
    combined = value
    while "]" not in combined and line_index + 1 < len(lines):
        line_index += 1
        combined += _strip_comment(lines[line_index])
    return combined, line_index


def _parse_string(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def atlas_png_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    )


def matching_toml_path(atlas_path: Path) -> Path | None:
    expected = atlas_path.with_suffix(".toml")
    if expected.exists():
        return expected
    for candidate in atlas_path.parent.iterdir():
        if candidate.stem == atlas_path.stem and candidate.suffix.lower() == ".toml":
            return candidate
    return None


def load_tile_metadata(folder: Path, atlas_filter: Path | None = None) -> list[TileDef]:
    tiles: list[TileDef] = []
    atlas_paths = (
        [atlas_filter] if atlas_filter is not None else atlas_png_files(folder)
    )
    for atlas_path in atlas_paths:
        metadata_path = matching_toml_path(atlas_path)
        if metadata_path is None:
            continue

        current_name: str | None = None
        current: dict[str, tuple[int, int]] = {}

        def commit() -> None:
            nonlocal current_name, current
            if current_name is None:
                return
            pos = current.get("pos")
            size = current.get("size")
            if pos is None or size is None:
                return
            tiles.append(
                TileDef(
                    name=current_name,
                    atlas_path=atlas_path,
                    pos=pos,
                    size=size,
                    frame_offset=current.get("frame_offset", (0, 0)),
                    frame_size=current.get("frame_size", (64, 128)),
                )
            )

        metadata_lines = metadata_path.read_text(encoding="utf-8").splitlines()
        line_index = 0
        while line_index < len(metadata_lines):
            line = _strip_comment(metadata_lines[line_index]).strip()
            if not line:
                line_index += 1
                continue
            if line.startswith("[") and line.endswith("]"):
                commit()
                current_name = line[1:-1].strip()
                current = {}
                line_index += 1
                continue
            if "=" not in line or current_name is None:
                line_index += 1
                continue
            key, value = line.split("=", 1)
            value, line_index = _collect_toml_array_value(
                metadata_lines, line_index, value
            )
            parsed = _parse_int_array(value)
            if parsed is not None:
                current[key.strip()] = parsed
            line_index += 1
        commit()
    return tiles


def texturepack_folders(root: Path = DEFAULT_TEXTUREPACKS_DIR) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and any(child.suffix.lower() == ".png" for child in path.iterdir())
    )


def save_map(path: Path, placements: dict[tuple[int, int, int, int], MapTile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Map generated by tools/map_editor.py",
        "# Coordinates are integer tile cells. level is vertical world level.",
        "",
    ]
    for level, layer, x, z in sorted(placements):
        tile = placements[(level, layer, x, z)]
        lines.append("[[tiles]]")
        lines.append(f"level = {level}")
        lines.append(f"layer = {layer}")
        lines.append(f"x = {x}")
        lines.append(f"z = {z}")
        lines.append(f"name = {_toml_string(tile.tile_name)}")
        lines.append(f"atlas = {_toml_string(tile.atlas_name)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_map(path: Path) -> dict[tuple[int, int, int, int], MapTile]:
    placements: dict[tuple[int, int, int, int], MapTile] = {}
    current: dict[str, int | str] | None = None

    def commit() -> None:
        nonlocal current
        if current is None:
            return
        level = current.get("level")
        x = current.get("x")
        z = current.get("z")
        layer = current.get("layer", 0)
        tile_name = current.get("name")
        atlas_name = current.get("atlas")
        if (
            isinstance(level, int)
            and isinstance(layer, int)
            and isinstance(x, int)
            and isinstance(z, int)
            and isinstance(tile_name, str)
            and isinstance(atlas_name, str)
        ):
            placements[(level, layer, x, z)] = MapTile(tile_name, atlas_name)
        current = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if line == "[[tiles]]":
            commit()
            current = {}
            continue
        if current is None or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if key in {"level", "layer", "x", "z"}:
            current[key] = int(value)
        elif key in {"name", "atlas"}:
            current[key] = _parse_string(value)
    commit()
    return placements


class MapEditor(tk.Tk):
    def __init__(
        self, initial_texturepack: Path | None, initial_map: Path | None
    ) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x860")
        self.state_data = EditorState()
        self.current_tile: TileDef | None = None
        self.atlas_images: dict[Path, tk.PhotoImage] = {}
        self.tile_image_cache: dict[
            tuple[Path, tuple[int, int], tuple[int, int], int], tk.PhotoImage
        ] = {}
        self.placement_images: list[tk.PhotoImage] = []
        self.tile_filter = tk.StringVar()
        self.selected_atlas = tk.StringVar(value="All atlases")
        self.selected_level = tk.IntVar(value=0)
        self.selected_layer = tk.IntVar(value=0)
        self.status = tk.StringVar(value="Open a texturepack folder to begin.")
        self.tile_filter.trace_add("write", lambda *_: self.refresh_tile_list())
        self.selected_level.trace_add("write", lambda *_: self.redraw_map())
        self.selected_layer.trace_add("write", lambda *_: self.redraw_map())
        self._build_ui()
        self.load_default_texturepack(initial_texturepack)
        if initial_map is not None:
            self.open_map(initial_map)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X)
        ttk.Button(
            toolbar, text="Open texturepack", command=self.choose_texturepack
        ).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open PNG atlas", command=self.choose_png).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Open map", command=self.choose_map).pack(
            side=tk.LEFT, padx=(18, 0)
        )
        ttk.Button(toolbar, text="Save map", command=self.save_current_map).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save map as", command=self.save_map_as).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(toolbar, text="Level").pack(side=tk.LEFT, padx=(18, 4))
        self.level_spin = ttk.Spinbox(
            toolbar,
            from_=MIN_LEVEL,
            to=MAX_LEVEL,
            width=5,
            textvariable=self.selected_level,
            command=self.redraw_map,
        )
        self.level_spin.pack(side=tk.LEFT)
        ttk.Label(toolbar, text="Layer").pack(side=tk.LEFT, padx=(8, 4))
        self.layer_spin = ttk.Spinbox(
            toolbar,
            from_=0,
            to=9,
            width=5,
            textvariable=self.selected_layer,
            command=self.redraw_map,
        )
        self.layer_spin.pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Clear level", command=self.clear_current_level).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Label(toolbar, textvariable=self.status).pack(side=tk.LEFT, padx=16)

        body = ttk.Frame(root)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        left = ttk.Frame(body, width=330)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Atlas").pack(anchor=tk.W)
        self.atlas_combo = ttk.Combobox(
            left, textvariable=self.selected_atlas, state="readonly"
        )
        self.atlas_combo.pack(fill=tk.X)
        self.atlas_combo.bind("<<ComboboxSelected>>", self.on_atlas_selected)
        ttk.Label(left, text="Tile filter").pack(anchor=tk.W, pady=(8, 0))
        ttk.Entry(left, textvariable=self.tile_filter).pack(fill=tk.X)
        self.tile_list = tk.Listbox(left, width=46)
        self.tile_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tile_list.bind("<<ListboxSelect>>", self.on_tile_selected)
        buttons = ttk.Frame(left)
        buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(buttons, text="Prev tile", command=self.select_previous_tile).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(buttons, text="Next tile", command=self.select_next_tile).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0)
        )

        center = ttk.Frame(body)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        self.map_canvas = tk.Canvas(center, bg="#202020", cursor="tcross")
        self.map_canvas.pack(fill=tk.BOTH, expand=True)
        self.map_canvas.bind("<Button-1>", self.on_place_tile)
        self.map_canvas.bind("<Button-3>", self.on_erase_tile)
        self.map_canvas.bind("<Motion>", self.on_map_motion)

        right = ttk.Frame(body, width=250)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(right, text="Selected tile").pack(anchor=tk.W)
        self.preview_canvas = tk.Canvas(right, width=220, height=220, bg="#303030")
        self.preview_canvas.pack(fill=tk.X, pady=(4, 8))
        ttk.Label(right, text="Placed tiles on this level").pack(anchor=tk.W)
        self.placed_list = tk.Listbox(right, width=34, height=24)
        self.placed_list.pack(fill=tk.BOTH, expand=True)
        self.placed_list.bind("<<ListboxSelect>>", self.on_placed_selected)
        ttk.Button(
            right,
            text="Delete selected placement",
            command=self.delete_selected_placement,
        ).pack(fill=tk.X, pady=(8, 0))

    def load_default_texturepack(self, initial_path: Path | None) -> None:
        if initial_path is not None:
            self.open_texturepack_path(initial_path)
            return
        folders = texturepack_folders()
        if folders:
            self.open_texturepack_folder(folders[0], atlas_filter=None)

    def choose_texturepack(self) -> None:
        initial = (
            DEFAULT_TEXTUREPACKS_DIR
            if DEFAULT_TEXTUREPACKS_DIR.exists()
            else Path.cwd()
        )
        selected = filedialog.askdirectory(
            title="Choose texturepack folder", initialdir=str(initial)
        )
        if selected:
            self.open_texturepack_path(Path(selected))

    def choose_png(self) -> None:
        initial = (
            DEFAULT_TEXTUREPACKS_DIR
            if DEFAULT_TEXTUREPACKS_DIR.exists()
            else Path.cwd()
        )
        selected = filedialog.askopenfilename(
            title="Choose one PNG atlas",
            initialdir=str(initial),
            filetypes=PNG_FILETYPES,
        )
        if selected:
            self.open_texturepack_path(Path(selected))

    def open_texturepack_path(self, path: Path) -> None:
        if path.is_file():
            if path.suffix.lower() != ".png":
                messagebox.showerror("Unsupported file", "Please select a .png atlas.")
                return
            self.open_texturepack_folder(path.parent, atlas_filter=path)
        else:
            self.open_texturepack_folder(path, atlas_filter=None)

    def open_texturepack_folder(self, folder: Path, atlas_filter: Path | None) -> None:
        tiles = load_tile_metadata(folder, atlas_filter)
        self.state_data.texturepack_folder = folder
        self.state_data.atlas_filter = atlas_filter
        self.state_data.tiles = tiles
        self.current_tile = None
        self.atlas_images.clear()
        self.tile_image_cache.clear()
        self.refresh_atlas_combo()
        self.refresh_tile_list()
        mode = atlas_filter.name if atlas_filter is not None else "all atlases"
        self.status.set(f"Loaded {len(tiles)} tile(s) from {mode} in {folder}")
        if self.filtered_tiles():
            self.select_tile_by_index(0)
        self.redraw_map()

    def refresh_atlas_combo(self) -> None:
        atlas_names = ["All atlases"]
        atlas_names.extend(
            sorted({tile.atlas_path.name for tile in self.state_data.tiles})
        )
        self.atlas_combo["values"] = atlas_names
        if self.state_data.atlas_filter is not None:
            self.selected_atlas.set(self.state_data.atlas_filter.name)
        else:
            self.selected_atlas.set("All atlases")

    def tile_visible_in_filters(self, tile: TileDef) -> bool:
        query = self.tile_filter.get().lower()
        atlas_name = self.selected_atlas.get()
        if atlas_name != "All atlases" and tile.atlas_path.name != atlas_name:
            return False
        return not query or query in tile.name.lower()

    def filtered_tiles(self) -> list[TileDef]:
        return [
            tile for tile in self.state_data.tiles if self.tile_visible_in_filters(tile)
        ]

    def refresh_tile_list(self) -> None:
        self.tile_list.delete(0, tk.END)
        for tile in self.filtered_tiles():
            self.tile_list.insert(tk.END, f"{tile.name}  [{tile.atlas_path.name}]")

    def selected_tile_index(self) -> int | None:
        selection = self.tile_list.curselection()
        if not selection:
            return None
        return selection[0]

    def select_tile_by_index(self, index: int) -> None:
        tiles = self.filtered_tiles()
        if not tiles:
            return
        index = max(0, min(len(tiles) - 1, index))
        self.tile_list.selection_clear(0, tk.END)
        self.tile_list.selection_set(index)
        self.tile_list.see(index)
        self.current_tile = tiles[index]
        self.redraw_preview()

    def select_next_tile(self) -> None:
        tiles = self.filtered_tiles()
        if not tiles:
            return
        index = self.selected_tile_index()
        self.select_tile_by_index(0 if index is None else (index + 1) % len(tiles))

    def select_previous_tile(self) -> None:
        tiles = self.filtered_tiles()
        if not tiles:
            return
        index = self.selected_tile_index()
        self.select_tile_by_index(
            len(tiles) - 1 if index is None else (index - 1) % len(tiles)
        )

    def on_atlas_selected(self, _event: tk.Event) -> None:
        self.refresh_tile_list()
        self.current_tile = None
        if self.filtered_tiles():
            self.select_tile_by_index(0)
        self.redraw_preview()

    def on_tile_selected(self, _event: tk.Event) -> None:
        index = self.selected_tile_index()
        tiles = self.filtered_tiles()
        self.current_tile = (
            tiles[index] if index is not None and index < len(tiles) else None
        )
        self.redraw_preview()

    def ensure_atlas_image(self, tile: TileDef) -> tk.PhotoImage:
        image = self.atlas_images.get(tile.atlas_path)
        if image is None:
            image = tk.PhotoImage(file=str(tile.atlas_path))
            self.atlas_images[tile.atlas_path] = image
        return image

    def tile_sprite_image(self, tile: TileDef, zoom: int = 1) -> tk.PhotoImage:
        cache_key = (tile.atlas_path, tile.pos, tile.size, zoom)
        cached = self.tile_image_cache.get(cache_key)
        if cached is not None:
            return cached

        atlas = self.ensure_atlas_image(tile)
        x, y = tile.pos
        width, height = tile.size
        cropped = atlas.copy(from_coords=(x, y, x + width, y + height))
        if zoom > 1:
            cropped = cropped.zoom(zoom, zoom)
        self.tile_image_cache[cache_key] = cropped
        return cropped

    def tile_by_saved_ref(self, saved_tile: MapTile) -> TileDef | None:
        for tile in self.state_data.tiles:
            if (
                tile.name == saved_tile.tile_name
                and tile.atlas_path.name == saved_tile.atlas_name
            ):
                return tile
        for tile in self.state_data.tiles:
            if tile.name == saved_tile.tile_name:
                return tile
        return None

    def redraw_preview(self) -> None:
        self.preview_canvas.delete("all")
        if self.current_tile is None:
            self.preview_canvas.create_text(
                12, 12, anchor=tk.NW, fill="white", text="Select a tile."
            )
            return
        tile = self.current_tile
        zoom = max(1, min(3, 180 // max(1, max(tile.size))))
        image = self.tile_sprite_image(tile, zoom=zoom)
        self.preview_image = image
        self.preview_canvas.create_image(110, 20, anchor=tk.N, image=image)
        self.preview_canvas.create_text(
            8,
            190,
            anchor=tk.SW,
            fill="#dddddd",
            width=210,
            text=f"{tile.name}\n{tile.atlas_path.name}",
        )

    def map_origin(self) -> tuple[int, int]:
        width = int(self.map_canvas.winfo_width() or 900)
        return width // 2, CANVAS_PADDING + MAP_HALF_SIZE * TILE_SCREEN_HEIGHT // 2

    def cell_to_screen(self, x: int, z: int) -> tuple[float, float]:
        origin_x, origin_y = self.map_origin()
        return (
            origin_x + (x - z) * TILE_SCREEN_WIDTH * 0.5,
            origin_y + (x + z) * TILE_SCREEN_HEIGHT * 0.5,
        )

    def screen_to_cell(self, screen_x: float, screen_y: float) -> tuple[int, int]:
        origin_x, origin_y = self.map_origin()
        dx = (screen_x - origin_x) / (TILE_SCREEN_WIDTH * 0.5)
        dz = (screen_y - origin_y) / (TILE_SCREEN_HEIGHT * 0.5)
        x = round((dx + dz) * 0.5)
        z = round((dz - dx) * 0.5)
        return x, z

    def current_level(self) -> int:
        try:
            return max(MIN_LEVEL, min(MAX_LEVEL, int(self.selected_level.get())))
        except tk.TclError:
            return 0

    def current_layer(self) -> int:
        try:
            return max(0, min(9, int(self.selected_layer.get())))
        except tk.TclError:
            return 0

    def redraw_map(self) -> None:
        self.map_canvas.delete("all")
        self.placement_images.clear()
        level = self.current_level()
        self.draw_world_grid(is_overlay=False)

        placements = [
            (layer, x, z, tile)
            for (tile_level, layer, x, z), tile in self.state_data.placements.items()
            if tile_level == level
        ]
        floor_placements = [item for item in placements if item[0] == 0]
        object_placements = [item for item in placements if item[0] != 0]
        for layer, x, z, saved_tile in sorted(
            floor_placements, key=lambda item: (item[1] + item[2], item[2])
        ):
            self.draw_placement(layer, x, z, saved_tile)

        # Draw a second grid after the floor layer. This keeps the world grid
        # visible under props/objects without drawing it over floor tiles.
        self.draw_world_grid(is_overlay=True)

        for layer, x, z, saved_tile in sorted(
            object_placements, key=lambda item: (item[0], item[1] + item[2], item[2])
        ):
            self.draw_placement(layer, x, z, saved_tile)
        self.refresh_placed_list()

    def draw_world_grid(self, is_overlay: bool) -> None:
        base_color = "#4a4a4a" if is_overlay else "#343434"
        axis_color = "#5d86bd" if is_overlay else "#456a9a"
        for x in range(-MAP_HALF_SIZE, MAP_HALF_SIZE + 1):
            self.draw_grid_line(x, -MAP_HALF_SIZE, x, MAP_HALF_SIZE, base_color)
        for z in range(-MAP_HALF_SIZE, MAP_HALF_SIZE + 1):
            self.draw_grid_line(-MAP_HALF_SIZE, z, MAP_HALF_SIZE, z, base_color)
        self.draw_grid_line(0, -MAP_HALF_SIZE, 0, MAP_HALF_SIZE, axis_color)
        self.draw_grid_line(-MAP_HALF_SIZE, 0, MAP_HALF_SIZE, 0, axis_color)

    def draw_grid_line(self, x0: int, z0: int, x1: int, z1: int, color: str) -> None:
        sx0, sy0 = self.cell_to_screen(x0, z0)
        sx1, sy1 = self.cell_to_screen(x1, z1)
        self.map_canvas.create_line(sx0, sy0, sx1, sy1, fill=color)

    def draw_cell_outline(self, x: int, z: int, color: str, width: int = 1) -> None:
        cx, cy = self.cell_to_screen(x, z)
        points = [
            cx,
            cy - TILE_SCREEN_HEIGHT * 0.5,
            cx + TILE_SCREEN_WIDTH * 0.5,
            cy,
            cx,
            cy + TILE_SCREEN_HEIGHT * 0.5,
            cx - TILE_SCREEN_WIDTH * 0.5,
            cy,
        ]
        self.map_canvas.create_polygon(points, outline=color, fill="", width=width)

    def draw_placement(self, layer: int, x: int, z: int, saved_tile: MapTile) -> None:
        outline = "#ffd000" if layer == self.current_layer() else "#4f8cff"
        self.draw_cell_outline(x, z, outline, width=2)
        tile = self.tile_by_saved_ref(saved_tile)
        cx, cy = self.cell_to_screen(x, z)
        if tile is None:
            self.map_canvas.create_text(
                cx,
                cy, 
                fill="#ff8080",
                text=f"L{layer}: {saved_tile.tile_name}",
                width=120,
            )
            return
        image = self.tile_sprite_image(tile)
        self.placement_images.append(image)
        self.map_canvas.create_image(cx, cy, anchor=tk.CENTER, image=image)

    def on_map_motion(self, event: tk.Event) -> None:
        x, z = self.screen_to_cell(event.x, event.y)
        self.status.set(
            f"Level {self.current_level()} layer {self.current_layer()} cell x={x} z={z}; left-click place, right-click erase"
        )

    def on_place_tile(self, event: tk.Event) -> None:
        if self.current_tile is None:
            messagebox.showinfo(
                "No tile selected", "Select a tile before painting the map."
            )
            return
        x, z = self.screen_to_cell(event.x, event.y)
        self.state_data.placements[
            (self.current_level(), self.current_layer(), x, z)
        ] = MapTile(self.current_tile.name, self.current_tile.atlas_path.name)
        self.redraw_map()

    def on_erase_tile(self, event: tk.Event) -> None:
        x, z = self.screen_to_cell(event.x, event.y)
        self.state_data.placements.pop(
            (self.current_level(), self.current_layer(), x, z), None
        )
        self.redraw_map()

    def refresh_placed_list(self) -> None:
        self.placed_list.delete(0, tk.END)
        level = self.current_level()
        for key in sorted(self.state_data.placements):
            tile_level, layer, x, z = key
            if tile_level != level:
                continue
            tile = self.state_data.placements[key]
            self.placed_list.insert(
                tk.END, f"layer={layer} x={x:>3} z={z:>3}  {tile.tile_name}"
            )

    def selected_placement_key(self) -> tuple[int, int, int, int] | None:
        selection = self.placed_list.curselection()
        if not selection:
            return None
        level = self.current_level()
        keys = [key for key in sorted(self.state_data.placements) if key[0] == level]
        index = selection[0]
        return keys[index] if index < len(keys) else None

    def on_placed_selected(self, _event: tk.Event) -> None:
        key = self.selected_placement_key()
        if key is None:
            return
        _level, _layer, x, z = key
        self.draw_cell_outline(x, z, "#ffd000", width=3)

    def delete_selected_placement(self) -> None:
        key = self.selected_placement_key()
        if key is None:
            return
        self.state_data.placements.pop(key, None)
        self.redraw_map()

    def clear_current_level(self) -> None:
        level = self.current_level()
        if not messagebox.askyesno(
            "Clear level", f"Delete all tiles on level {level}?"
        ):
            return
        for key in [key for key in self.state_data.placements if key[0] == level]:
            del self.state_data.placements[key]
        self.redraw_map()

    def choose_map(self) -> None:
        selected = filedialog.askopenfilename(
            title="Open saved map",
            initialdir=str(DEFAULT_SAVES_DIR),
            filetypes=MAP_FILETYPES,
        )
        if selected:
            self.open_map(Path(selected))

    def open_map(self, path: Path) -> None:
        self.state_data.placements = load_map(path)
        self.state_data.map_path = path
        self.status.set(
            f"Loaded map {path} with {len(self.state_data.placements)} tile(s)"
        )
        self.redraw_map()

    def save_current_map(self) -> None:
        if self.state_data.map_path is None:
            self.save_map_as()
            return
        save_map(self.state_data.map_path, self.state_data.placements)
        self.status.set(f"Saved {self.state_data.map_path}")

    def save_map_as(self) -> None:
        DEFAULT_SAVES_DIR.mkdir(parents=True, exist_ok=True)
        name = simpledialog.askstring("Map name", "Save map as", initialvalue="map_01")
        if not name:
            return
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "map"
        path = DEFAULT_SAVES_DIR / f"{safe_name}.toml"
        save_map(path, self.state_data.placements)
        self.state_data.map_path = path
        self.status.set(f"Saved {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and edit saved maps.")
    parser.add_argument(
        "texturepack",
        nargs="?",
        type=Path,
        help="Texturepack folder or one PNG atlas inside media/texturepacks",
    )
    parser.add_argument(
        "--map",
        dest="map_path",
        type=Path,
        help="Existing saves/*.toml map to open",
    )
    args = parser.parse_args()
    app = MapEditor(args.texturepack, args.map_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
