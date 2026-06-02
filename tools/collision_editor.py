#!/usr/bin/env python3
"""Small Tkinter editor for Project Zomboid-style tile collision metadata.

Open a Tiles1x-like folder containing atlas PNG files and matching TOML files,
select a tile, draw simple collision shapes over it, then save collisions.toml.
The generated file is intentionally simple so the C++ prototype can load it.
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
COLLISION_FILE_NAME = "collisions.toml"


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


@dataclass
class EditorState:
    folder: Path | None = None
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


def load_tile_metadata(folder: Path) -> list[TileDef]:
    tiles: list[TileDef] = []
    for atlas_path in sorted(folder.glob("*.png")):
        metadata_path = atlas_path.with_suffix(".toml")
        if not metadata_path.exists() or metadata_path.name == COLLISION_FILE_NAME:
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

        for raw_line in metadata_path.read_text(encoding="utf-8").splitlines():
            line = _strip_comment(raw_line).strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                commit()
                current_name = line[1:-1].strip()
                current = {}
                continue
            if "=" not in line or current_name is None:
                continue
            key, value = line.split("=", 1)
            parsed = _parse_int_array(value)
            if parsed is not None:
                current[key.strip()] = parsed
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
                lines.append(f"radius = {(shape.radius if shape.radius is not None else 0.25):.4f}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


class CollisionEditor(tk.Tk):
    def __init__(self, initial_folder: Path | None) -> None:
        super().__init__()
        self.title("Project Zomboid Collision Editor")
        self.geometry("1100x760")
        self.state_data = EditorState()
        self.current_tile: TileDef | None = None
        self.current_atlas: tk.PhotoImage | None = None
        self.drag_start: tuple[int, int] | None = None
        self.shape_type = tk.StringVar(value="aabb")
        self.status = tk.StringVar(value="Open a Tiles1x folder to begin.")
        self.tile_filter = tk.StringVar()
        self.tile_filter.trace_add("write", lambda *_: self.refresh_tile_list())
        self._build_ui()
        if initial_folder is not None:
            self.open_folder(initial_folder)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Open folder", command=self.choose_folder).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Save collisions.toml", command=self.save).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.status).pack(side=tk.LEFT, padx=16)

        body = ttk.Frame(root)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        left = ttk.Frame(body, width=300)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Tile filter").pack(anchor=tk.W)
        ttk.Entry(left, textvariable=self.tile_filter).pack(fill=tk.X)
        self.tile_list = tk.Listbox(left, width=42)
        self.tile_list.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tile_list.bind("<<ListboxSelect>>", self.on_tile_selected)

        center = ttk.Frame(body)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        self.canvas = tk.Canvas(center, bg="#202020", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_preview)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        right = ttk.Frame(body, width=280)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(right, text="Shape type").pack(anchor=tk.W)
        for label, value in (("Rectangle / AABB", "aabb"), ("Circle", "circle"), ("Full tile", "full_tile")):
            ttk.Radiobutton(right, text=label, variable=self.shape_type, value=value).pack(anchor=tk.W)
        ttk.Button(right, text="Add full-tile collision", command=self.add_full_tile).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(right, text="Delete selected shape", command=self.delete_selected_shape).pack(fill=tk.X, pady=(4, 0))
        ttk.Label(right, text="Shapes for selected tile").pack(anchor=tk.W, pady=(16, 0))
        self.shape_list = tk.Listbox(right, width=36, height=18)
        self.shape_list.pack(fill=tk.BOTH, expand=True)
        self.shape_list.bind("<<ListboxSelect>>", lambda _event: self.redraw_canvas())

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose Tiles1x folder")
        if selected:
            self.open_folder(Path(selected))

    def open_folder(self, folder: Path) -> None:
        try:
            tiles = load_tile_metadata(folder)
        except Exception as exc:  # noqa: BLE001 - UI should show parser errors.
            messagebox.showerror("Could not load tiles", str(exc))
            return
        self.state_data.folder = folder
        self.state_data.tiles = tiles
        self.state_data.collisions = load_collisions(folder / COLLISION_FILE_NAME)
        self.current_tile = None
        self.status.set(f"Loaded {len(tiles)} tile(s) from {folder}")
        self.refresh_tile_list()
        self.redraw_canvas()

    def refresh_tile_list(self) -> None:
        self.tile_list.delete(0, tk.END)
        query = self.tile_filter.get().lower()
        for tile in self.state_data.tiles:
            if not query or query in tile.name.lower():
                self.tile_list.insert(tk.END, tile.name)

    def selected_tile_name(self) -> str | None:
        selection = self.tile_list.curselection()
        if not selection:
            return None
        return self.tile_list.get(selection[0])

    def on_tile_selected(self, _event: tk.Event) -> None:
        name = self.selected_tile_name()
        self.current_tile = next((tile for tile in self.state_data.tiles if tile.name == name), None)
        self.current_atlas = None
        self.refresh_shape_list()
        self.redraw_canvas()

    def refresh_shape_list(self) -> None:
        self.shape_list.delete(0, tk.END)
        if self.current_tile is None:
            return
        for index, shape in enumerate(self.state_data.collisions.get(self.current_tile.name, []), start=1):
            if shape.type == "circle":
                self.shape_list.insert(
                    tk.END,
                    f"{index}. circle center={shape.center} r={shape.radius:.3f}",
                )
            else:
                self.shape_list.insert(
                    tk.END, f"{index}. {shape.type} min={shape.min} max={shape.max}"
                )

    def canvas_size(self) -> tuple[int, int]:
        if self.current_tile is None:
            return 1, 1
        return self.current_tile.size[0] * ZOOM, self.current_tile.size[1] * ZOOM

    def redraw_canvas(
        self, preview: tuple[int, int, int, int] | None = None
    ) -> None:
        self.canvas.delete("all")
        if self.current_tile is None:
            self.canvas.create_text(
                20, 20, anchor=tk.NW, fill="white", text="Select a tile."
            )
            return
        tile = self.current_tile
        width, height = self.canvas_size()
        self.canvas.config(scrollregion=(0, 0, width, height))
        if self.current_atlas is None:
            self.current_atlas = tk.PhotoImage(file=str(tile.atlas_path))
        zoomed = self.current_atlas.zoom(ZOOM, ZOOM)
        self.canvas._zoomed_atlas = zoomed  # keep Tk image alive
        self.canvas.create_image(
            -tile.pos[0] * ZOOM, -tile.pos[1] * ZOOM, anchor=tk.NW, image=zoomed
        )
        self.canvas.create_rectangle(0, 0, width, height, outline="#d0d0d0")
        for step in range(1, GRID_STEPS):
            x = width * step / GRID_STEPS
            y = height * step / GRID_STEPS
            self.canvas.create_line(x, 0, x, height, fill="#555555")
            self.canvas.create_line(0, y, width, y, fill="#555555")
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

    def draw_shape(self, shape: CollisionShape, color: str) -> None:
        width, height = self.canvas_size()
        if shape.type in {"aabb", "full_tile"} and shape.min and shape.max:
            x0, y0 = shape.min[0] * width, shape.min[1] * height
            x1, y1 = shape.max[0] * width, shape.max[1] * height
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=2)
        elif shape.type == "circle" and shape.center and shape.radius is not None:
            cx, cy = shape.center[0] * width, shape.center[1] * height
            radius = shape.radius * min(width, height)
            self.canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                outline=color, width=2
            )

    def normalized_rect(
        self, coords: tuple[int, int, int, int]
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        width, height = self.canvas_size()
        x0, y0, x1, y1 = coords
        min_x, max_x = sorted((max(0, min(width, x0)), max(0, min(width, x1))))
        min_y, max_y = sorted((max(0, min(height, y0)), max(0, min(height, y1))))
        return (min_x / width, min_y / height), (max_x / width, max_y / height)

    def on_drag_start(self, event: tk.Event) -> None:
        if self.current_tile is None:
            return
        self.drag_start = (event.x, event.y)

    def on_drag_preview(self, event: tk.Event) -> None:
        if self.drag_start is None:
            return
        x0, y0 = self.drag_start
        self.redraw_canvas((x0, y0, event.x, event.y))

    def on_drag_end(self, event: tk.Event) -> None:
        if self.current_tile is None or self.drag_start is None:
            return
        x0, y0 = self.drag_start
        self.drag_start = None
        min_point, max_point = self.normalized_rect(
            (x0, y0, event.x, event.y)
        )
        if (
            abs(max_point[0] - min_point[0]) < 0.01
            or abs(max_point[1] - min_point[1]) < 0.01
        ):
            self.redraw_canvas()
            return
        shape_type = self.shape_type.get()
        if shape_type == "circle":
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
            shape = CollisionShape(
                type="full_tile", min=(0.0, 0.0), max=(1.0, 1.0)
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
        self.state_data.collisions.setdefault(self.current_tile.name, []).append(
            CollisionShape(
                type="full_tile", min=(0.0, 0.0), max=(1.0, 1.0)
            )
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
        "folder", nargs="?", type=Path,
        help="Tiles folder with PNG/TOML atlas metadata"
    )
    args = parser.parse_args()
    app = CollisionEditor(args.folder)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
