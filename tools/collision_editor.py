#!/usr/bin/env python3
"""Tile collision metadata editor for the C++ Project Zomboid prototype.

The editor opens either a Tiles1x-style folder or one atlas PNG. It reads the
matching TOML metadata, cuts the atlas into individual tile sprites, displays the
selected tile with an in-game-like projected cell guide, and writes normalized
collision shapes to collisions.toml next to the atlas metadata.
"""

from __future__ import annotations

import argparse
import re
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ZOOM = 4
GRID_STEPS = 4
CANVAS_PADDING = 48
COLLISION_FILE_NAME = "collisions.toml"
PNG_FILETYPES = (("PNG atlas", ("*.png", "*.PNG")), ("All files", "*.*"))


@dataclass
class TileDef:
    name: str
    atlas_path: Path
    pos: tuple[int, int]
    size: tuple[int, int]
    frame_offset: tuple[int, int] = (0, 0)
    frame_size: tuple[int, int] = (64, 128)


@dataclass
class CollisionShape:
    type: str
    min: tuple[float, float] | None = None
    max: tuple[float, float] | None = None
    center: tuple[float, float] | None = None
    radius: float | None = None
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None
    thickness: float | None = None


@dataclass
class EditorState:
    folder: Path | None = None
    atlas_filter: Path | None = None
    tiles: list[TileDef] = field(default_factory=list)
    collisions: dict[str, list[CollisionShape]] = field(default_factory=dict)


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


def _parse_float_array(value: str) -> tuple[float, float] | None:
    numbers = [float(match) for match in re.findall(r"-?\d+(?:\.\d+)?", value)]
    if len(numbers) < 2:
        return None
    return numbers[0], numbers[1]


def _parse_string(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return value


def atlas_png_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path for path in folder.iterdir()
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
    atlas_paths = [atlas_filter] if atlas_filter is not None else atlas_png_files(folder)
    for atlas_path in atlas_paths:
        metadata_path = matching_toml_path(atlas_path)
        if metadata_path is None or metadata_path.name == COLLISION_FILE_NAME:
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


def load_collisions(path: Path) -> dict[str, list[CollisionShape]]:
    collisions: dict[str, list[CollisionShape]] = {}
    if not path.exists():
        return collisions

    current_tile: str | None = None
    current_shape: CollisionShape | None = None

    def commit_shape() -> None:
        nonlocal current_shape
        if current_tile is None or current_shape is None:
            return
        collisions.setdefault(current_tile, []).append(current_shape)
        current_shape = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if line == "[[tiles]]":
            commit_shape()
            current_tile = None
            continue
        if line == "[[tiles.shapes]]":
            commit_shape()
            current_shape = CollisionShape(type="aabb")
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if key == "name":
            commit_shape()
            current_tile = _parse_string(value)
            collisions.setdefault(current_tile, [])
        elif current_shape is not None and key == "type":
            current_shape.type = _parse_string(value)
        elif current_shape is not None and key == "min":
            current_shape.min = _parse_float_array(value)
        elif current_shape is not None and key == "max":
            current_shape.max = _parse_float_array(value)
        elif current_shape is not None and key == "center":
            current_shape.center = _parse_float_array(value)
        elif current_shape is not None and key == "radius":
            current_shape.radius = float(value)
        elif current_shape is not None and key == "start":
            current_shape.start = _parse_float_array(value)
        elif current_shape is not None and key == "end":
            current_shape.end = _parse_float_array(value)
        elif current_shape is not None and key == "thickness":
            current_shape.thickness = float(value)
    commit_shape()
    return collisions


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_vec2(value: tuple[float, float]) -> str:
    return f"[{value[0]:.4f}, {value[1]:.4f}]"


def save_collisions(path: Path, collisions: dict[str, list[CollisionShape]]) -> None:
    lines = [
        "# Collision metadata generated by tools/collision_editor.py",
        "# Coordinates are normalized to the visible tile sprite: [0, 0] is top-left, [1, 1] is bottom-right.",
        "",
    ]
    for tile_name in sorted(name for name, shapes in collisions.items() if shapes):
        lines.append("[[tiles]]")
        lines.append(f"name = {_toml_string(tile_name)}")
        for shape in collisions[tile_name]:
            lines.append("")
            lines.append("[[tiles.shapes]]")
            lines.append(f"type = {_toml_string(shape.type)}")
            if shape.type in {"aabb", "full_tile"}:
                lines.append(f"min = {_toml_vec2(shape.min or (0.0, 0.0))}")
                lines.append(f"max = {_toml_vec2(shape.max or (1.0, 1.0))}")
            elif shape.type == "circle":
                lines.append(f"center = {_toml_vec2(shape.center or (0.5, 0.5))}")
                radius = shape.radius if shape.radius is not None else 0.25
                lines.append(f"radius = {radius:.4f}")
            elif shape.type == "segment":
                lines.append(f"start = {_toml_vec2(shape.start or (0.5, 0.0))}")
                lines.append(f"end = {_toml_vec2(shape.end or (0.5, 1.0))}")
                thickness = shape.thickness if shape.thickness is not None else 0.05
                lines.append(f"thickness = {thickness:.4f}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


class CollisionEditor(tk.Tk):
    def __init__(self, initial_path: Path | None) -> None:
        super().__init__()
        self.title("Project Zomboid Collision Editor")
        self.geometry("1180x820")
        self.state_data = EditorState()
        self.current_tile: TileDef | None = None
        self.current_atlas_path: Path | None = None
        self.current_atlas: tk.PhotoImage | None = None
        self.current_tile_image: tk.PhotoImage | None = None
        self.drag_start: tuple[int, int] | None = None
        self.shape_type = tk.StringVar(value="aabb")
        self.status = tk.StringVar(value="Open a folder or one PNG atlas to begin.")
        self.tile_filter = tk.StringVar()
        self.selected_atlas = tk.StringVar(value="All atlases")
        self.tile_filter.trace_add("write", lambda *_: self.refresh_tile_list())
        self._build_ui()
        if initial_path is not None:
            self.open_path(initial_path)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Open folder", command=self.choose_folder).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Open PNG atlas", command=self.choose_png).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save collisions.toml", command=self.save).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Prev tile", command=self.select_previous_tile).pack(
            side=tk.LEFT, padx=(18, 0)
        )
        ttk.Button(toolbar, text="Next tile", command=self.select_next_tile).pack(
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
        self.tile_list.bind(
            "<Double-Button-1>", lambda _event: self.redraw_canvas()
        )

        center = ttk.Frame(body)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        self.canvas = tk.Canvas(center, bg="#202020", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_preview)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        right = ttk.Frame(body, width=290)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(right, text="Shape type").pack(anchor=tk.W)
        for label, value in (
            ("Rectangle / AABB", "aabb"),
            ("Circle", "circle"),
            ("Side / wall line", "segment"),
            ("Full tile", "full_tile"),
        ):
            ttk.Radiobutton(
                right, text=label, variable=self.shape_type, value=value
            ).pack(anchor=tk.W)
        ttk.Button(
            right, text="Add full-tile collision", command=self.add_full_tile
        ).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            right, text="Delete selected shape", command=self.delete_selected_shape
        ).pack(fill=tk.X, pady=(4, 0))
        ttk.Label(right, text="Shapes for selected tile").pack(
            anchor=tk.W, pady=(16, 0)
        )
        self.shape_list = tk.Listbox(right, width=38, height=18)
        self.shape_list.pack(fill=tk.BOTH, expand=True)
        self.shape_list.bind(
            "<<ListboxSelect>>", lambda _event: self.redraw_canvas()
        )

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose Tiles1x folder")
        if selected:
            self.open_path(Path(selected))

    def choose_png(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose one PNG atlas", filetypes=PNG_FILETYPES
        )
        if selected:
            self.open_path(Path(selected))

    def open_path(self, path: Path) -> None:
        if path.is_file():
            if path.suffix.lower() != ".png":
                messagebox.showerror("Unsupported file", "Please select a .png atlas.")
                return
            self.open_folder(path.parent, atlas_filter=path)
        else:
            self.open_folder(path, atlas_filter=None)

    def open_folder(self, folder: Path, atlas_filter: Path | None) -> None:
        try:
            tiles = load_tile_metadata(folder, atlas_filter)
        except Exception as exc:  # noqa: BLE001 - UI should show parser errors.
            messagebox.showerror("Could not load tiles", str(exc))
            return
        self.state_data.folder = folder
        self.state_data.atlas_filter = atlas_filter
        self.state_data.tiles = tiles
        self.state_data.collisions = load_collisions(folder / COLLISION_FILE_NAME)
        self.current_tile = None
        self.current_atlas = None
        self.current_atlas_path = None
        self.current_tile_image = None
        self.refresh_atlas_combo()
        self.refresh_tile_list()
        mode = atlas_filter.name if atlas_filter is not None else "all atlases"
        self.status.set(f"Loaded {len(tiles)} tile(s) from {mode} in {folder}")
        if self.filtered_tiles():
            self.select_tile_by_index(0)
        else:
            self.redraw_canvas()

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

    def on_atlas_selected(self, _event: tk.Event) -> None:
        self.refresh_tile_list()
        self.current_tile = None
        self.current_tile_image = None
        if self.filtered_tiles():
            self.select_tile_by_index(0)
        else:
            self.refresh_shape_list()
            self.redraw_canvas()

    def tile_visible_in_filters(self, tile: TileDef) -> bool:
        query = self.tile_filter.get().lower()
        atlas_name = self.selected_atlas.get()
        if atlas_name != "All atlases" and tile.atlas_path.name != atlas_name:
            return False
        return not query or query in tile.name.lower()

    def filtered_tiles(self) -> list[TileDef]:
        return [
            tile
            for tile in self.state_data.tiles
            if self.tile_visible_in_filters(tile)
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
        self.current_tile_image = None
        self.refresh_shape_list()
        self.redraw_canvas()

    def select_next_tile(self) -> None:
        tiles = self.filtered_tiles()
        if not tiles:
            return
        index = self.selected_tile_index()
        self.select_tile_by_index(
            0 if index is None else (index + 1) % len(tiles)
        )

    def select_previous_tile(self) -> None:
        tiles = self.filtered_tiles()
        if not tiles:
            return
        index = self.selected_tile_index()
        self.select_tile_by_index(
            len(tiles) - 1 if index is None else (index - 1) % len(tiles)
        )

    def on_tile_selected(self, _event: tk.Event) -> None:
        index = self.selected_tile_index()
        tiles = self.filtered_tiles()
        self.current_tile = (
            tiles[index] if index is not None and index < len(tiles) else None
        )
        self.current_tile_image = None
        self.refresh_shape_list()
        self.redraw_canvas()

    def refresh_shape_list(self) -> None:
        self.shape_list.delete(0, tk.END)
        if self.current_tile is None:
            return
        shapes = self.state_data.collisions.get(self.current_tile.name, [])
        for index, shape in enumerate(shapes, start=1):
            if shape.type == "circle":
                self.shape_list.insert(
                    tk.END,
                    f"{index}. circle center={shape.center} r={shape.radius:.3f}",
                )
            elif shape.type == "segment":
                self.shape_list.insert(
                    tk.END,
                    f"{index}. segment start={shape.start} end={shape.end}",
                )
            else:
                self.shape_list.insert(
                    tk.END, f"{index}. {shape.type} min={shape.min} max={shape.max}"
                )

    def sprite_size(self) -> tuple[int, int]:
        if self.current_tile is None:
            return 1, 1
        return self.current_tile.size[0] * ZOOM, self.current_tile.size[1] * ZOOM

    def sprite_origin(self) -> tuple[int, int]:
        return CANVAS_PADDING, CANVAS_PADDING

    def ensure_atlas_image(self, tile: TileDef) -> tk.PhotoImage:
        if self.current_atlas is None or self.current_atlas_path != tile.atlas_path:
            self.current_atlas = tk.PhotoImage(file=str(tile.atlas_path))
            self.current_atlas_path = tile.atlas_path
            self.current_tile_image = None
        return self.current_atlas

    def tile_sprite_image(self, tile: TileDef) -> tk.PhotoImage:
        if self.current_tile_image is not None:
            return self.current_tile_image
        atlas = self.ensure_atlas_image(tile)
        x, y = tile.pos
        width, height = tile.size
        cropped = atlas.copy(from_coords=(x, y, x + width, y + height))
        self.current_tile_image = cropped.zoom(ZOOM, ZOOM)
        return self.current_tile_image

    def redraw_canvas(
        self, preview: tuple[int, int, int, int] | None = None
    ) -> None:
        self.canvas.delete("all")
        if self.current_tile is None:
            message = "Select a tile or open one PNG atlas."
            if self.state_data.folder is not None and not self.state_data.tiles:
                message = (
                    "No tiles were loaded. Open a PNG that has a matching .toml "
                    "file with pos/size entries, or open the folder containing both."
                )
            elif self.state_data.tiles:
                message = "No tile matches the current atlas/filter selection."
            self.canvas.create_text(
                20,
                20,
                anchor=tk.NW,
                fill="white",
                text=message,
                width=720,
            )
            return

        tile = self.current_tile
        sprite_width, sprite_height = self.sprite_size()
        origin_x, origin_y = self.sprite_origin()
        canvas_width = sprite_width + CANVAS_PADDING * 2
        canvas_height = sprite_height + CANVAS_PADDING * 2
        self.canvas.config(scrollregion=(0, 0, canvas_width, canvas_height))
        self.canvas.create_image(
            origin_x, origin_y, anchor=tk.NW, image=self.tile_sprite_image(tile)
        )
        self.draw_projected_cell_guide(
            origin_x, origin_y, sprite_width, sprite_height
        )
        self.canvas.create_rectangle(
            origin_x, origin_y, origin_x + sprite_width, origin_y + sprite_height,
            outline="#d0d0d0",
        )
        self.draw_sprite_grid(origin_x, origin_y, sprite_width, sprite_height)
        self.canvas.create_text(
            origin_x,
            16,
            anchor=tk.NW,
            fill="#dddddd",
            text=f"{tile.name}  ({tile.atlas_path.name})",
        )

        selected = self.shape_list.curselection()
        selected_index = selected[0] if selected else -1
        for index, shape in enumerate(
            self.state_data.collisions.get(tile.name, [])
        ):
            color = "#00ff88" if index == selected_index else "#ff4040"
            self.draw_shape(shape, color)
        if preview is not None:
            self.canvas.create_rectangle(
                *preview, outline="#ffd000", width=2, dash=(4, 3)
            )

    def projected_cell_rect_pixels(self) -> tuple[float, float, float, float]:
        origin_x, origin_y = self.sprite_origin()
        sprite_width, sprite_height = self.sprite_size()
        diamond_width = sprite_width
        diamond_height = sprite_width * 0.5
        center_x = origin_x + sprite_width * 0.5
        center_y = origin_y + max(
            diamond_height * 0.5, sprite_height - diamond_height * 0.5
        )
        return (
            center_x - diamond_width * 0.5,
            center_y - diamond_height * 0.5,
            center_x + diamond_width * 0.5,
            center_y + diamond_height * 0.5,
        )

    def projected_cell_rect_normalized(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        origin_x, origin_y = self.sprite_origin()
        sprite_width, sprite_height = self.sprite_size()
        left, top, right, bottom = self.projected_cell_rect_pixels()
        return (
            (
                (left - origin_x) / sprite_width,
                (top - origin_y) / sprite_height,
            ),
            (
                (right - origin_x) / sprite_width,
                (bottom - origin_y) / sprite_height,
            ),
        )

    def draw_projected_cell_guide(
        self, origin_x: int, origin_y: int, sprite_width: int, sprite_height: int
    ) -> None:
        left, top, right, bottom = self.projected_cell_rect_pixels()
        center_x = (left + right) * 0.5
        center_y = (top + bottom) * 0.5
        diamond_width = right - left
        diamond_height = bottom - top
        points = [
            center_x, center_y - diamond_height * 0.5,
            center_x + diamond_width * 0.5, center_y,
            center_x, center_y + diamond_height * 0.5,
            center_x - diamond_width * 0.5, center_y,
        ]
        self.canvas.create_polygon(points, outline="#4f8cff", fill="", width=2)
        for step in range(1, GRID_STEPS):
            t = step / GRID_STEPS
            left_x = center_x - diamond_width * 0.5 * (1.0 - t)
            left_y = center_y - diamond_height * 0.5 * t
            right_x = center_x + diamond_width * 0.5 * t
            right_y = center_y - diamond_height * 0.5 * (1.0 - t)
            self.canvas.create_line(
                left_x, left_y, right_x, right_y, fill="#315070"
            )
            left_x = center_x - diamond_width * 0.5 * t
            left_y = center_y + diamond_height * 0.5 * (1.0 - t)
            right_x = center_x + diamond_width * 0.5 * (1.0 - t)
            right_y = center_y + diamond_height * 0.5 * t
            self.canvas.create_line(
                left_x, left_y, right_x, right_y, fill="#315070"
            )

    def draw_sprite_grid(
        self, origin_x: int, origin_y: int, sprite_width: int, sprite_height: int
    ) -> None:
        for step in range(1, GRID_STEPS):
            x = origin_x + sprite_width * step / GRID_STEPS
            y = origin_y + sprite_height * step / GRID_STEPS
            self.canvas.create_line(
                x, origin_y, x, origin_y + sprite_height, fill="#555555"
            )
            self.canvas.create_line(
                origin_x, y, origin_x + sprite_width, y, fill="#555555"
            )

    def draw_shape(self, shape: CollisionShape, color: str) -> None:
        sprite_width, sprite_height = self.sprite_size()
        origin_x, origin_y = self.sprite_origin()
        if shape.type in {"aabb", "full_tile"} and shape.min and shape.max:
            x0 = origin_x + shape.min[0] * sprite_width
            y0 = origin_y + shape.min[1] * sprite_height
            x1 = origin_x + shape.max[0] * sprite_width
            y1 = origin_y + shape.max[1] * sprite_height
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
        elif shape.type == "circle" and shape.center and shape.radius is not None:
            cx = origin_x + shape.center[0] * sprite_width
            cy = origin_y + shape.center[1] * sprite_height
            radius = shape.radius * min(sprite_width, sprite_height)
            self.canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                outline=color, width=2,
            )
        elif shape.type == "segment" and shape.start and shape.end:
            x0 = origin_x + shape.start[0] * sprite_width
            y0 = origin_y + shape.start[1] * sprite_height
            x1 = origin_x + shape.end[0] * sprite_width
            y1 = origin_y + shape.end[1] * sprite_height
            thickness = max(
                2,
                int((shape.thickness or 0.05) * min(sprite_width, sprite_height)),
            )
            self.canvas.create_line(x0, y0, x1, y1, fill=color, width=thickness)

    def clamp_to_sprite(self, x: int, y: int) -> tuple[int, int]:
        origin_x, origin_y = self.sprite_origin()
        sprite_width, sprite_height = self.sprite_size()
        return (
            max(origin_x, min(origin_x + sprite_width, x)),
            max(origin_y, min(origin_y + sprite_height, y)),
        )

    def normalized_point(self, x: int, y: int) -> tuple[float, float]:
        origin_x, origin_y = self.sprite_origin()
        sprite_width, sprite_height = self.sprite_size()
        clamped_x, clamped_y = self.clamp_to_sprite(x, y)
        return (
            (clamped_x - origin_x) / sprite_width,
            (clamped_y - origin_y) / sprite_height,
        )

    def normalized_rect(
        self, coords: tuple[int, int, int, int]
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        origin_x, origin_y = self.sprite_origin()
        sprite_width, sprite_height = self.sprite_size()
        x0, y0 = self.clamp_to_sprite(coords[0], coords[1])
        x1, y1 = self.clamp_to_sprite(coords[2], coords[3])
        min_x, max_x = sorted((x0, x1))
        min_y, max_y = sorted((y0, y1))
        return (
            (
                (min_x - origin_x) / sprite_width,
                (min_y - origin_y) / sprite_height,
            ),
            (
                (max_x - origin_x) / sprite_width,
                (max_y - origin_y) / sprite_height,
            ),
        )

    def on_drag_start(self, event: tk.Event) -> None:
        if self.current_tile is None:
            return
        self.drag_start = self.clamp_to_sprite(event.x, event.y)

    def on_drag_preview(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        x0, y0 = self.drag_start
        x1, y1 = self.clamp_to_sprite(event.x, event.y)
        if self.shape_type.get() == "segment":
            self.redraw_canvas()
            self.canvas.create_line(x0, y0, x1, y1, fill="#ffd000", width=4)
        else:
            self.redraw_canvas((x0, y0, x1, y1))

    def on_drag_end(self, event: tk.Event) -> None:
        if self.current_tile is None or self.drag_start is None:
            return
        x0, y0 = self.drag_start
        x1, y1 = self.clamp_to_sprite(event.x, event.y)
        self.drag_start = None
        shape_type = self.shape_type.get()
        min_point, max_point = self.normalized_rect((x0, y0, x1, y1))
        if shape_type == "segment":
            start = self.normalized_point(x0, y0)
            end = self.normalized_point(x1, y1)
            if (
                abs(end[0] - start[0]) < 0.01
                and abs(end[1] - start[1]) < 0.01
            ):
                self.redraw_canvas()
                return
            shape = CollisionShape(
                type="segment", start=start, end=end, thickness=0.05
            )
        elif (
            abs(max_point[0] - min_point[0]) < 0.01
            or abs(max_point[1] - min_point[1]) < 0.01
        ):
            self.redraw_canvas()
            return
        elif shape_type == "circle":
            center = (
                (min_point[0] + max_point[0]) * 0.5,
                (min_point[1] + max_point[1]) * 0.5,
            )
            radius = (
                min(max_point[0] - min_point[0], max_point[1] - min_point[1])
                * 0.5
            )
            shape = CollisionShape(type="circle", center=center, radius=radius)
        elif shape_type == "full_tile":
            min_point, max_point = self.projected_cell_rect_normalized()
            shape = CollisionShape(
                type="full_tile", min=min_point, max=max_point
            )
        else:
            shape = CollisionShape(type="aabb", min=min_point, max=max_point)
        self.state_data.collisions.setdefault(self.current_tile.name, []).append(
            shape
        )
        self.refresh_shape_list()
        self.redraw_canvas()

    def add_full_tile(self) -> None:
        if self.current_tile is None:
            return
        min_point, max_point = self.projected_cell_rect_normalized()
        self.state_data.collisions.setdefault(self.current_tile.name, []).append(
            CollisionShape(type="full_tile", min=min_point, max=max_point)
        )
        self.refresh_shape_list()
        self.redraw_canvas()

    def delete_selected_shape(self) -> None:
        if self.current_tile is None:
            return
        selection = self.shape_list.curselection()
        if not selection:
            return
        shapes = self.state_data.collisions.get(self.current_tile.name, [])
        del shapes[selection[0]]
        self.refresh_shape_list()
        self.redraw_canvas()

    def save(self) -> None:
        if self.state_data.folder is None:
            return
        path = self.state_data.folder / COLLISION_FILE_NAME
        save_collisions(path, self.state_data.collisions)
        self.status.set(f"Saved {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit tile collision metadata.")
    parser.add_argument(
        "path", nargs="?", type=Path,
        help="Tiles folder or one PNG atlas with matching TOML metadata",
    )
    args = parser.parse_args()
    app = CollisionEditor(args.path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
